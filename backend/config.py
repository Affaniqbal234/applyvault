import os
from dataclasses import dataclass
from ipaddress import ip_network
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@dataclass(frozen=True)
class Settings:
    environment: str
    jwt_secret: str
    origins: tuple[str, ...]
    proxy_ips: str


def load_settings():
    environment = os.environ.get("APP_ENV", "development")
    if environment not in {"development", "production"}:
        raise RuntimeError("APP_ENV must be development or production")
    secret = os.environ.get("JWT_SECRET", "")
    if len(secret.encode()) < 32 or secret != secret.strip():
        raise RuntimeError("JWT_SECRET must contain at least 32 bytes without surrounding whitespace")
    origins = tuple(part.strip() for part in os.environ.get("FRONTEND_ORIGIN", "").split(","))
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None or parsed.path or parsed.query
            or parsed.fragment or "*" in origin or "\\" in origin or any(char.isspace() for char in origin)
        ):
            raise RuntimeError("FRONTEND_ORIGIN must contain explicit HTTP(S) origins without paths")
        try:
            parsed.port
        except ValueError:
            raise RuntimeError("FRONTEND_ORIGIN contains an invalid port") from None
        if environment == "production" and parsed.scheme != "https":
            raise RuntimeError("Production frontend origins must use HTTPS")
    if environment == "production" and not os.environ.get("DATABASE_URL", "").startswith(
        ("postgresql://", "postgresql+asyncpg://", "postgres://")
    ):
        raise RuntimeError("Production requires a PostgreSQL DATABASE_URL")
    proxy_ips = os.environ.get("TRUSTED_PROXY_IPS", "").strip()
    for value in proxy_ips.split(",") if proxy_ips else []:
        try:
            network = ip_network(value.strip(), strict=False)
            if network.prefixlen == 0:
                raise ValueError
        except ValueError:
            raise RuntimeError("TRUSTED_PROXY_IPS must contain explicit proxy IPs or networks, never a wildcard") from None
    return Settings(environment, secret, origins, proxy_ips)


settings = load_settings()

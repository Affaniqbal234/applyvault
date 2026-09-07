"""Build public frontend files using an explicitly configured API origin."""
import argparse
import json
import os
from pathlib import Path
import shutil
from urllib.parse import urlsplit


def build(api_url, output):
    parsed = urlsplit(api_url)
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
        or parsed.password is not None or parsed.path not in {"", "/"} or parsed.query
        or parsed.fragment or any(char.isspace() for char in api_url)
        or "\\" in api_url or "*" in api_url
    ):
        raise ValueError("API_URL must be an HTTPS origin without credentials, query, or path")
    parsed.port  # Reject malformed ports before writing any files.
    source = Path(__file__).resolve().parents[1] / "frontend"
    output = Path(output).resolve()
    if output == source or source in output.parents:
        raise ValueError("Build output must be separate from frontend source")
    output.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "dashboard.html", "app.js", "style.css"):
        shutil.copyfile(source / name, output / name)
    config = json.dumps({"apiUrl": f"{parsed.scheme}://{parsed.netloc}"})
    (output / "config.js").write_text(f"window.APPLYVAULT_CONFIG = {config};\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("dist/frontend"))
    args = parser.parse_args()
    try:
        build(os.environ.get("API_URL", ""), args.output)
    except ValueError as error:
        parser.error(str(error))

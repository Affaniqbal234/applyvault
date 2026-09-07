import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User

JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET environment variable is not set. "
        "Set it to a random secret string before starting."
    )

ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=24)
    return pyjwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = pyjwt.decode(
            token, JWT_SECRET, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]}
        )
        subject = payload["sub"]
        if (
            not isinstance(subject, str)
            or not subject.isascii()
            or not subject.isdecimal()
            or len(subject) > 10
        ):
            raise InvalidTokenError("Invalid subject")
        user_id = int(subject)
        # User.id is a PostgreSQL INTEGER; reject overflow before querying it.
        if not 1 <= user_id <= 2_147_483_647:
            raise InvalidTokenError("Invalid subject")
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except (InvalidTokenError, TypeError, ValueError, OverflowError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user

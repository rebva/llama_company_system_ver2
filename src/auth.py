"""
認証・ユーザー管理まわりの共通処理。
- パスワードハッシュ化
- JWT 発行・検証
- FastAPI 依存性 (get_current_user / get_current_admin)
"""
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from src.config import JWT_SECRET, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from src.database import get_db
from src.models import User, TokenData

security = HTTPBearer()


def hash_pw(password: str) -> str:
    """SECRET を塩代わりにした簡易ハッシュ（デモ用）"""
    data = (JWT_SECRET + password).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def verify_pw(plain_password: str, hashed_password: str) -> bool:
    """ハッシュを比較（timing-attack 対策で compare_digest を使用）"""
    data = (JWT_SECRET + plain_password).encode("utf-8")
    calc = hashlib.sha256(data).hexdigest()
    return hmac.compare_digest(calc, hashed_password)


def create_access_token(username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def create_user(db: Session, username: str, password: str, role: str = "user") -> User:
    hashed_pw = hash_pw(password)
    user = User(username=username, hashed_password=hashed_pw, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not verify_pw(password, user.hashed_password):
        return None
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    Authorization: Bearer <token> を受け取ってユーザを特定。
    """
    token = credentials.credentials

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user = get_user_by_username(db, token_data.username)
    if user is None:
        raise credentials_exception
    return user


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    role='admin' のユーザだけを許可する dependency。
    それ以外は 403 Forbidden。
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user

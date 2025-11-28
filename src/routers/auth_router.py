"""
認証系エンドポイント (/login, /register) をまとめた router。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.auth import (
    authenticate_user,
    create_access_token,
    create_user,
    get_user_by_username,
)
from src.database import get_db
from src.models import LoginRequest, RegisterRequest, RegisterResponse, Token

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=Token)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, req.username, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    access_token = create_access_token(user.username, user.role)
    return Token(access_token=access_token, token_type="bearer")


@router.post("/register", response_model=RegisterResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """
    新しいユーザを登録する API。
    """
    if get_user_by_username(db, req.username) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    create_user(db, req.username, req.password)
    return RegisterResponse(username=req.username)

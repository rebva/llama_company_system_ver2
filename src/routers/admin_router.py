"""
管理系エンドポイント (/admin/users)。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.auth import get_current_admin
from src.database import get_db
from src.models import UserInfo, User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserInfo])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),  # admin のみ
):
    """登録済みユーザの一覧を返す。"""
    users = db.query(User).order_by(User.id).all()
    return users

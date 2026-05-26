"""文件说明：FastAPI 路由模块，提供 auth 相关的 HTTP 接口和权限校验。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
from ..database import get_db
from ..models.user import User
from ..schemas.user import UserLogin, UserRegister, Token, UserResponse
from ..utils.security import verify_password, get_password_hash, create_access_token, get_current_user
from ..config import settings

router = APIRouter()

def build_token_response(user: User) -> dict:
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }

@router.post("/login", response_model=Token)
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == user_data.username).first()
    
    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    if user.status == "disabled":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用"
        )
    
    return build_token_response(user)

@router.post("/register", response_model=Token)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    username = user_data.username.strip()
    password = user_data.password

    if len(username) < 3 or len(username) > 50:
        raise HTTPException(status_code=400, detail="用户名长度需为 3-50 个字符")
    if any(ch.isspace() for ch in username):
        raise HTTPException(status_code=400, detail="用户名不能包含空白字符")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码至少需要 6 位")

    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=username,
        password_hash=get_password_hash(password),
        role="user",
        status="active"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return build_token_response(user)

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/logout")
def logout(current_user: User = Depends(get_current_user)):
    # JWT 是无状态的，客户端删除 token 即可
    return {"message": "退出成功"}

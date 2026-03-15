from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from ..models.user import User
from ..models.conversation import Conversation
from ..models.message import Message
from ..schemas.user import UserCreate, UserUpdate, UserResponse
from ..utils.security import get_current_admin, get_password_hash

router = APIRouter()

@router.get("/stats")
def get_stats(db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    """获取统计数据"""
    user_count = db.query(User).filter(User.role == "user").count()
    conversation_count = db.query(Conversation).count()
    message_count = db.query(Message).count()
    
    return {
        "user_count": user_count,
        "conversation_count": conversation_count,
        "message_count": message_count
    }

@router.get("/users", response_model=List[UserResponse])
def get_users(db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    """获取用户列表"""
    users = db.query(User).filter(User.role == "user").order_by(User.created_at.desc()).all()
    return users

@router.post("/users", response_model=UserResponse)
def create_user(user_data: UserCreate, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    """创建用户"""
    # 检查用户名是否已存在
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    user = User(
        username=user_data.username,
        password_hash=get_password_hash(user_data.password),
        role="user",
        status="active"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(user_id: int, user_data: UserUpdate, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    """更新用户"""
    user = db.query(User).filter(User.id == user_id, User.role == "user").first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    if user_data.status:
        user.status = user_data.status
    if user_data.password:
        user.password_hash = get_password_hash(user_data.password)
    
    db.commit()
    db.refresh(user)
    return user

@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    """删除用户"""
    user = db.query(User).filter(User.id == user_id, User.role == "user").first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    db.delete(user)
    db.commit()
    return {"message": "删除成功"}

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import time
import json
from datetime import datetime
from ..database import get_db
from ..models.user import User
from ..models.conversation import Conversation
from ..models.message import Message
from ..schemas.conversation import ConversationCreate, ConversationResponse, ConversationUpdate
from ..schemas.message import MessageCreate, MessageFeedbackUpdate, MessageResponse, MessageWithTraceResponse
from ..schemas.inference import InferenceModelSelectRequest
from ..utils.security import get_current_chat_user
from ..services.inference_service import InferenceCancelledError, inference_service

router = APIRouter()


def build_message_response(message: Message, trace_payload=None) -> MessageResponse:
    if trace_payload is None and message.inference_trace:
        try:
            trace_payload = json.loads(message.inference_trace)
        except Exception:
            trace_payload = None
    feedback = message.feedback if message.feedback in ("like", "dislike") else None
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        reasoning_content=message.reasoning_content,
        raw_content=message.raw_content,
        inference_trace=trace_payload,
        feedback=feedback,
        created_at=message.created_at,
    )

@router.get("/inference/status")
def get_inference_status(current_user: User = Depends(get_current_chat_user)):
    """查看推理链路状态（调试用）"""
    return inference_service.debug_status()


@router.get("/inference/trace")
def get_inference_trace(current_user: User = Depends(get_current_chat_user)):
    """查看最近一次推理的阶段埋点"""
    return inference_service.trace_status()


@router.get("/inference/models")
def get_inference_models(current_user: User = Depends(get_current_chat_user)):
    """查看可切换模型列表"""
    return {
        "current_model_id": inference_service.debug_status().get("current_model_id"),
        "models": inference_service.list_models(),
    }


@router.post("/inference/model/select")
def select_inference_model(
    data: InferenceModelSelectRequest,
    current_user: User = Depends(get_current_chat_user),
):
    """切换当前推理模型"""
    try:
        return inference_service.select_model(data.model_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/inference/cancel")
def cancel_inference(current_user: User = Depends(get_current_chat_user)):
    """停止当前推理，但保持模型进程在线"""
    result = inference_service.request_cancel()
    if not result.get("accepted"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result.get("detail") or "取消失败")
    return result

@router.get("/conversations", response_model=List[ConversationResponse])
def get_conversations(db: Session = Depends(get_db), current_user: User = Depends(get_current_chat_user)):
    """获取用户的对话列表"""
    conversations = db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).order_by(Conversation.updated_at.desc()).all()
    return conversations

@router.post("/conversations", response_model=ConversationResponse)
def create_conversation(
    data: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_chat_user)
):
    """创建新对话"""
    conversation = Conversation(
        user_id=current_user.id,
        title=data.title or "新对话"
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation

@router.put("/conversations/{conversation_id}", response_model=ConversationResponse)
def update_conversation(
    conversation_id: int,
    data: ConversationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_chat_user)
):
    """更新对话信息"""
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")

    title = (data.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="对话名称不能为空")

    conversation.title = title[:255]
    conversation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(conversation)
    return conversation

@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_chat_user)
):
    """删除对话"""
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")
    
    db.delete(conversation)
    db.commit()
    return {"message": "删除成功"}

@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageResponse])
def get_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_chat_user)
):
    """获取对话消息"""
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")
    
    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()
    
    return [build_message_response(msg) for msg in messages]


@router.put("/messages/{message_id}/feedback", response_model=MessageResponse)
def update_message_feedback(
    message_id: int,
    data: MessageFeedbackUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_chat_user),
):
    """标记消息点赞/点踩。再次点击同类标记时前端会传空值取消。"""
    message = db.query(Message).join(
        Conversation,
        Message.conversation_id == Conversation.id,
    ).filter(
        Message.id == message_id,
        Conversation.user_id == current_user.id,
    ).first()

    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")

    message.feedback = data.feedback
    db.commit()
    db.refresh(message)
    return build_message_response(message)

@router.post("/conversations/{conversation_id}/messages", response_model=MessageWithTraceResponse)
def send_message(
    conversation_id: int,
    data: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_chat_user)
):
    """发送消息并获取AI回复"""
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")
    
    # 保存用户消息
    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=data.content
    )
    db.add(user_message)
    db.commit()
    
    # 获取历史消息用于上下文
    history_messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()
    
    history = [{"role": msg.role, "content": msg.content} for msg in history_messages]
    if len(history) <= 1:
        conversation.title = data.content[:50] + ("..." if len(data.content) > 50 else "")
        db.commit()
    
    # 调用推理引擎
    infer_start = time.monotonic()
    try:
        ai_raw_response = inference_service.generate(
            data.content,
            history,
            think_enabled=data.think_enabled,
            conversation_id=conversation_id,
        )
    except InferenceCancelledError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except Exception as exc:
        ai_raw_response = f"推理异常: {exc}"
    parsed_response = inference_service.parse_assistant_response(ai_raw_response)
    ai_response = parsed_response.get("content") or "（模型未生成有效回复）"
    infer_elapsed = time.monotonic() - infer_start
    if not ai_response.strip():
        ai_response = "（模型未生成有效回复）"
    print(
        f"[Chat] conversation={conversation_id} user={current_user.id} "
        f"infer_elapsed={infer_elapsed:.2f}s response_chars={len(ai_response)}"
    )
    
    # 保存AI回复
    trace_payload = inference_service.trace_status()
    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=ai_response,
        reasoning_content=parsed_response.get("reasoning_content"),
        raw_content=parsed_response.get("raw_content"),
        inference_trace=json.dumps(trace_payload, ensure_ascii=False) if trace_payload else None,
    )
    db.add(assistant_message)
    
    db.commit()
    db.refresh(assistant_message)
    
    return MessageWithTraceResponse(**build_message_response(assistant_message, trace_payload).model_dump())

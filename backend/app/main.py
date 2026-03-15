from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import auth, admin, chat
from .database import engine, Base
from .config import settings

# 创建数据库表
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Chat Platform", version="1.0.0")

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(admin.router, prefix="/api/admin", tags=["管理员"])
app.include_router(chat.router, prefix="/api", tags=["对话"])

@app.get("/")
def root():
    return {"message": "AI Chat Platform API"}

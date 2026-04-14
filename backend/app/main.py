import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import auth, admin, chat
from .database import engine, Base, ensure_database_schema
from .config import settings


class SuppressAccessLogPathsFilter(logging.Filter):
    def __init__(self, suppressed_paths: set[str]):
        super().__init__()
        self.suppressed_paths = suppressed_paths

    def filter(self, record: logging.LogRecord) -> bool:
        args = getattr(record, "args", ())
        if not isinstance(args, tuple) or len(args) < 3:
            return True
        request_path = str(args[2]).split("?", 1)[0]
        return request_path not in self.suppressed_paths


def configure_logging() -> None:
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    suppressed_paths = settings.ACCESS_LOG_SUPPRESSED_PATHS
    if not suppressed_paths:
        return

    access_logger = logging.getLogger("uvicorn.access")
    has_same_filter = any(
        isinstance(existing_filter, SuppressAccessLogPathsFilter)
        and existing_filter.suppressed_paths == suppressed_paths
        for existing_filter in access_logger.filters
    )
    if not has_same_filter:
        access_logger.addFilter(SuppressAccessLogPathsFilter(suppressed_paths))


configure_logging()

# 创建数据库表
Base.metadata.create_all(bind=engine)
ensure_database_schema()

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

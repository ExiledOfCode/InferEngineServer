from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings

engine = create_engine(settings.DATABASE_URL, echo=settings.SQL_ECHO)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_database_schema():
    inspector = inspect(engine)
    try:
        table_names = set(inspector.get_table_names())
    except Exception as exc:
        print(f"[DB] 获取表结构失败: {exc}")
        return

    if "messages" not in table_names:
        return

    try:
        columns = {column["name"] for column in inspector.get_columns("messages")}
    except Exception as exc:
        print(f"[DB] 获取 messages 字段失败: {exc}")
        return

    statements = []
    if "reasoning_content" not in columns:
        statements.append("ALTER TABLE messages ADD COLUMN reasoning_content TEXT NULL")
    if "raw_content" not in columns:
        statements.append("ALTER TABLE messages ADD COLUMN raw_content TEXT NULL")

    if not statements:
        return

    try:
        with engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))
    except Exception as exc:
        print(f"[DB] 自动补齐消息字段失败: {exc}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

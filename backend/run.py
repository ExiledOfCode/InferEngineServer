"""文件说明：后端开发运行入口，启动 Uvicorn 承载 FastAPI 应用。"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

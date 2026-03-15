# AI 对话平台

基于 Vue 3 + FastAPI + MySQL 的 AI 对话平台。

## 项目结构

```
server/
├── backend/          # Python FastAPI 后端
├── web/              # Vue 3 前端
└── sql/              # 数据库初始化脚本
```

## 快速开始

### 1. 初始化数据库

```bash
# 登录 MySQL
mysql -u root -p

# 执行初始化脚本
source server/sql/init.sql
```

### 2. 启动后端

```bash
cd server/backend

# 安装依赖
pip install -r requirements.txt

cd server/backend

# 启动服务
python run.py
```

后端服务运行在 http://localhost:8000

### 3. 启动前端

```bash
cd server/web

# 安装依赖
npm install


cd server/web

# 启动开发服务器
npm run dev -- --host
```

前端服务运行在 http://localhost:5173

可选前端环境变量（`server/web/.env`）：

```env
# 前端直接请求后端时使用，例如 http://127.0.0.1:8000/api
VITE_API_BASE_URL=
# API 超时（毫秒）
VITE_API_TIMEOUT=300000
# 打开浏览器控制台 API 调试日志
VITE_API_DEBUG=false
# Vite dev proxy 目标地址
VITE_PROXY_TARGET=http://127.0.0.1:8000
```

说明：

- 若未设置 `VITE_API_BASE_URL`，前端会先请求 `/api`（适合 `npm run dev` 走 Vite proxy）。
- 当 `/api` 不通时，前端会自动回退到 `http://<当前主机>:8000/api`、`http://127.0.0.1:8000/api`、`http://localhost:8000/api`，用于 `vite preview` 或直接静态部署场景。
- 建议排障时设置 `VITE_API_DEBUG=true`，浏览器控制台会打印实际请求地址与回退过程。

## 默认账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | admin | admin |

## 配置说明

### 后端配置

编辑 `backend/app/config.py` 或创建 `.env` 文件：

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=123456
DB_NAME=ai_chat
SECRET_KEY=your-secret-key
# 可选：逗号分隔的精确 Origin 白名单
CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
# 可选：Origin 正则（本地调试建议保留默认）
CORS_ALLOW_ORIGIN_REGEX=^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168\.\d+\.\d+)(:\d+)?$
# 推理生成长度（默认 128，过小会导致回复很短）
INFERENCE_MAX_NEW_TOKENS=128
# 是否在后端启动时立即加载模型（默认 false，避免大模型拖慢/阻塞 API 启动）
INFERENCE_EAGER_START=false
# prompt 格式：auto（默认，Instruct 模型自动走 chatml）、chatml、raw
INFERENCE_PROMPT_FORMAT=auto
# 可选：chatml 下的 system 提示词
INFERENCE_SYSTEM_PROMPT=You are a helpful assistant.
# raw 模式是否拼接历史上下文（默认 false）
INFERENCE_RAW_WITH_HISTORY=false
# 可选：指定模型目录（相对 INFERENCE_ENGINE_PATH/models）
INFERENCE_MODEL_DIR=Qwen2.5-0.5B
# 可选：直接指定模型文件（优先级高于 INFERENCE_MODEL_DIR）
# INFERENCE_MODEL_PATH=/mnt/d/.../KuiperLLama/models/Qwen2.5-0.5B/Qwen2.5-0.5B.bin
# 可选：直接指定 tokenizer（未配置时会在模型目录自动查找）
# INFERENCE_TOKENIZER_PATH=/mnt/d/.../KuiperLLama/models/Qwen2.5-0.5B/tokenizer.json
```

### 推理引擎配置

修改 `backend/app/config.py` 中的 `INFERENCE_ENGINE_PATH` 指向你的推理引擎路径。
当 `models/` 下存在多个模型时，推荐在 `config.py` 或 `.env` 中设置 `INFERENCE_MODEL_DIR` 来固定目标模型。

## API 文档

启动后端后访问：http://localhost:8000/docs

# 启动平台
## 项目结构

```text
server/
├── backend/          # Python FastAPI 后端
├── web/              # Vue 3 前端
└── sql/              # 数据库初始化脚本
```

## 启动平台

```bash
# 1. 修改 config 文件
# server/backend/app/config.py

# 2. 初始化数据库（在仓库根目录执行）
mysql -u root -p < server/sql/init.sql

# 3. 启动后端
cd server/backend
pip install -r requirements.txt
cd server/backend
python run.py

# 4. 启动前端（新终端）
cd server/web
npm install
cd server/web
npm run dev -- --host

# 5. 访问
# 前端: http://localhost:5173
# 后端 API 文档: http://localhost:8000/docs
```

## 默认账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | admin | admin |

## 配置前端

```bash
# Vue 3 / Node.js 20
apt update
apt install -y curl ca-certificates

curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
node -v
npm -v

npm install -g pnpm
pnpm -v
```

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
- 当 `/api` 不通时，前端会自动回退到 `http://<当前主机>:8000/api`、`http://127.0.0.1:8000/api`、`http://localhost:8000/api`。
- 排障时建议设置 `VITE_API_DEBUG=true`，浏览器控制台会打印实际请求地址与回退过程。

## 配置后端

```bash
# MySQL
apt update
apt install -y mysql-server
service mysql start
mysql --version
mysql -u root

mysql
ALTER USER 'root'@'localhost' IDENTIFIED BY '123456';
FLUSH PRIVILEGES;
EXIT;
```

后端关键配置位于 `server/backend/app/config.py`（也支持 `.env`）：

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
# 是否在后端启动时立即加载模型
INFERENCE_EAGER_START=false
# prompt 格式：auto / chatml / raw
INFERENCE_PROMPT_FORMAT=auto
# chatml 模式系统提示词
INFERENCE_SYSTEM_PROMPT=You are a helpful assistant.
# raw 模式是否拼接历史上下文
INFERENCE_RAW_WITH_HISTORY=false

# 可选：指定模型目录（相对 INFERENCE_ENGINE_PATH/models）
INFERENCE_MODEL_DIR=Qwen2.5-0.5B
# 可选：直接指定模型文件（优先级高于 INFERENCE_MODEL_DIR）
# INFERENCE_MODEL_PATH=/mnt/d/.../KuiperLLama/models/Qwen2.5-0.5B/Qwen2.5-0.5B.bin
# 可选：直接指定 tokenizer（未配置时会在模型目录自动查找）
# INFERENCE_TOKENIZER_PATH=/mnt/d/.../KuiperLLama/models/Qwen2.5-0.5B/tokenizer.json
```

## 配置推理框架

```bash
# armadillo
cd ./armadillo
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j8
make install
./tests1/smoke_test

# googletest
cd ./googletest
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j8
make install

# glog
cd ./glog
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release -DWITH_GFLAGS=OFF -DWITH_GTEST=OFF ..
make -j8
make install

# sentencepiece
cd ./sentencepiece
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j8
make install

# 安装 hf-hub 并导出模型
pip3 install -U huggingface_hub
huggingface-cli download --resume-download Qwen/Qwen2.5-0.5B --local-dir Qwen/Qwen2.5-0.5B --local-dir-use-symlinks False
python3 tools/export_qwen2.py Qwen2.5-0.5B.bin --hf=Qwen/Qwen2.5-0.5B

# 编译 server 使用的推理引擎
mkdir build
cd build
cmake -DLLAMA2_SUPPORT=ON ..
make -j16
# make -j$(nproc)

./build/demo/chat_server /workspace/Open_Source_Projects/MyInferenceEngine/KuiperLLama/Qwen2.5-0.5B.bin /workspace/Open_Source_Projects/MyInferenceEngine/KuiperLLama/Qwen/Qwen2.5-0.5B/tokenizer.json
```

## 配置 Clash

```bash
mkdir -p ~/.config/mihomo
# 复制配置文件和数据库到默认目录
cp config.yaml Country.mmdb ~/.config/mihomo/
# 可选：复制日志文件（一般不需要，除非你想保留旧日志）
cp mihomo.log ~/.config/mihomo/
# 将可执行文件复制到用户 bin 目录（方便全局调用）
mkdir -p ~/.local/bin
cp mihomo ~/.local/bin/
chmod +x ~/.local/bin/mihomo

# 后台运行
nohup ~/.local/bin/mihomo -d ~/.config/mihomo > ~/.config/mihomo/mihomo.log 2>&1 &

# 查看是否成功
ps aux | grep mihomo
```

## API 文档

启动后端后访问：`http://localhost:8000/docs`

# Server Benchmark Scripts

这些脚本只使用 Python 标准库，报告会写入 `server/test/benchmark_reports`。

先启动后端：

```bash
cd server/backend
python run.py
```

管理员接口示例：

```bash
python3 server/test/benchmarks/bench_auth_api.py --username admin --password admin
python3 server/test/benchmarks/bench_status_api.py --role admin --username admin --password admin
python3 server/test/benchmarks/bench_admin_options_api.py --username admin --password admin --write-check
```

普通用户对话接口需要 `user` 角色账号，或者直接传用户 token：

```bash
python3 server/test/benchmarks/bench_chat_api.py --username user1 --password your_password --repeat 3
python3 server/test/benchmarks/bench_model_switch_api.py --username user1 --password your_password --limit 2
python3 server/test/benchmarks/bench_load_progress_poll_api.py --username user1 --password your_password --poll-interval 0.5
```

也可以用环境变量：

```bash
export SERVER_BENCH_BASE_URL=http://127.0.0.1:8000/api
export SERVER_BENCH_TOKEN=...
```

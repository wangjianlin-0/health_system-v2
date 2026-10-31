# 部署文档

## 环境要求

Python 3.10+；Node.js 20.19+ 或 22.12+；Docker 可选。依据[根 README](../../README.md)。

## 快速部署

后端必须从仓库根目录执行：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe run_backend.py
```

另开终端：

```powershell
cd frontend
npm ci
npm run dev
```

没有默认账号，先注册。默认数据位于仓库 runtime/，可用 HEALTH_DB_PATH 指定数据库文件。API 文档：http://127.0.0.1:8000/docs 。现有 .venv 若失效，需要重建；不能据此认定应用已通过本轮验证。

## Docker 部署

从仓库根目录执行：

```powershell
docker compose -f business_logic/deploy/docker-compose.yml up --build -d
```

Compose 仅含后端，绑定本机 8000 端口，命名卷保存 runtime；构建上下文为根目录。Docker 尚未运行验收。前端在 frontend 执行 npm run build 后另配静态服务及 /api 代理；现有 nginx.conf 只配置 API 代理。

## TODO

- [ ] 容器构建、持久化与重启验证。
- [ ] 前端静态服务、代理及备份恢复。
- [ ] 生产并发与配置验收；Kubernetes 非首版前置条件。

记录模块维护业务框架与存储，账户模块维护身份授权，各作者共同联调。

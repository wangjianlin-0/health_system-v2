# 前后端启动指南

本文按本机 Windows + PowerShell 环境整理，覆盖**一次性准备、启动、验证、停止、常见报错**。接口与数据边界以[根 README](../README.md)、[接口契约](../interfaces/api_contract.md)和[验证记录](VALIDATION.md)为准。

## 0. 先看结论

- 后端：FastAPI，默认 `http://127.0.0.1:8000`，必须**从仓库根目录**启动。
- 前端：React + Vite，默认 `http://127.0.0.1:5173`，必须**在 `frontend` 目录**启动。
- 浏览器访问的是 **5173**，页面里的 `/api` 由 Vite 代理到 8000；直接打开 `index.html` 不行。
- 两个进程要分别开两个 PowerShell 窗口，先起后端，再起前端。

```text
浏览器 5173 ── /api/* ──► Vite 代理 ──► FastAPI 8000 ──► runtime/health.sqlite3
```

## 1. 环境说明

### 1.1 版本要求

| 组件 | 要求 | 本机示例 |
|---|---|---|
| Python | 3.10+ | `.venv` 为 3.13，`.venv-tasks` 为 3.12 |
| Node.js | 20.19+ 或 22.12+（26 也能跑，但非官方推荐） | v26.4.0 |
| PowerShell | Windows 自带即可 | 管理员或普通用户均可 |

### 1.2 两个虚拟环境的区别

仓库里有本机两个环境，**用哪个环境启动，就决定了有没有 AI 模型**：

| 环境 | 已装内容 | 用途 |
|---|---|---|
| `.venv-tasks` | 基础后端依赖（FastAPI、pytest 等） | 只做页面/接口联调；`openecg` 未安装，记录会显示“未接入模型” |
| `.venv` | 基础依赖 + `openecg[report]` | 需要真实分类、心率时使用；本机已验证 500 Hz CSV 可出结果 |

> 这两个环境是当前机器的现状；如果你的机器只有一个虚拟环境，按“有没有装 openecg”来理解即可，命令里的解释器路径换成你自己的。

> `.env` 里写 `ECG_MODEL_TYPE=openecg` **不会自动安装模型包**。只写配置但用 `.venv-tasks` 启动时，后端会降级为 `model_unavailable`，这是预期行为。

### 1.3 关键目录

| 路径 | 内容 |
|---|---|
| `business_logic/` | 后端 FastAPI 应用、服务、迁移、脚本 |
| `frontend/` | React + Vite 前端 |
| `runtime/health.sqlite3` | SQLite 数据库（不提交） |
| `runtime/uploads/` | 上传的原始 CSV（不提交） |
| `runtime/backups/` | 备份文件（不提交） |
| `.env` | 本机配置，不提交 |

## 2. 一次性准备

已经装好依赖可以跳过；换机器或新建环境时执行：

```powershell
cd C:\Users\wsg\Desktop\health_system-v2

# 基础依赖（测试 + 后端）
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 需要真实分类时，再装 AI 依赖（体积较大）
.venv\Scripts\python.exe -m pip install -r requirements-ai.txt
```

前端依赖：

```powershell
cd C:\Users\wsg\Desktop\health_system-v2\frontend
npm.cmd ci
```

配置文件：首次使用复制模板，已有 `.env` 不要覆盖。

```powershell
cd C:\Users\wsg\Desktop\health_system-v2
Copy-Item .env.example .env
```

`.env` 里和启动相关的几行：

```ini
ECG_MODEL_TYPE=openecg          # none 表示不加载模型；openecg 需要当前环境装了 openecg
ECG_EXPLANATION_PROVIDER=template
ECG_AUDIT_RETENTION_DAYS=90     # 访问审计保留天数
```

## 3. 启动（两个窗口）

### 3.1 窗口 1：后端

```powershell
cd C:\Users\wsg\Desktop\health_system-v2
.venv\Scripts\python.exe run_backend.py
```

如果要真实分类，必须用装了 `openecg` 的 `.venv`；如果只看页面/接口，用 `.venv-tasks` 也可以：

```powershell
.venv-tasks\Scripts\python.exe run_backend.py
```

正常输出类似：

```text
INFO:     Started server process [22616]
INFO:     Waiting for application startup.
INFO ecg 任务运行器已启动：workers=1
INFO ecg 启动完成 schema=5 applied=[] purged_audit=0 recovered_pending=0 interrupted=0
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

**这个窗口不要关**；关掉就等于停后端。

### 3.2 窗口 2：前端

```powershell
cd C:\Users\wsg\Desktop\health_system-v2\frontend
npm.cmd run dev
```

正常输出：

```text
VITE v6.4.4  ready in 237 ms
➜  Local:   http://127.0.0.1:5173/
```

浏览器打开 **http://127.0.0.1:5173/**。

> 为什么用 `npm.cmd`：Windows PowerShell 默认禁止运行 `npm.ps1`，会报 `因为在此系统上禁止运行脚本`。`npm.cmd` 不经过 PowerShell 脚本策略，所以能直接用。也可以在单个窗口临时放开：
>
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> npm run dev
> ```

### 3.3 入口代码

后端入口 [`run_backend.py`](../run_backend.py) 会先把 `business_logic` 加进 `sys.path`，再从仓库根目录启动：

```python
"""从仓库根目录启动，以便同时导入业务、硬件、信号与模型包。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'business_logic'))

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app.main:app', host='127.0.0.1', port=8000)
```

后端应用在 `app/main.py` 里做三件事：初始化/迁移数据库、恢复任务、启动进程内任务队列。核心片段：

```python
@asynccontextmanager
async def lifespan(app):
    _guard_single_process()
    configure(settings.log_level)
    info = initialize()              # 建库/迁移到最新版本
    purged = purge_audit_log()       # 按保留天数清理审计
    recovered = recover_tasks()      # pending 重新入队，running 标记中断
    runner.start()                   # 单 worker 后台任务
    for task_id in recovered['pending']:
        runner.enqueue(task_id)
    try:
        yield
    finally:
        runner.stop()
```

前端 Vite 配置 [`frontend/vite.config.ts`](../frontend/vite.config.ts) 负责把 `/api` 代理到 8000，并规避 Windows 下文件监听的 `EBUSY`：

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {'/api': 'http://127.0.0.1:8000'},
    // Windows 下原子写会产生临时目录/文件，fs.watch 会报 EBUSY；改用轮询
    watch: {usePolling: true, interval: 300, ignored: ['**/.*.tmpdir/**', '**/*.tmp']},
  },
});
```

前端脚本在 [`frontend/package.json`](../frontend/package.json)：

```json
"scripts": {
  "dev": "vite --host 127.0.0.1 --configLoader runner",
  "build": "tsc --noEmit && vite build --configLoader runner"
}
```

## 4. 打开后怎么验证

### 4.1 三个地址

| 地址 | 用途 | 正常表现 |
|---|---|---|
| http://127.0.0.1:5173/ | 前端页面 | 出现登录/注册页 |
| http://127.0.0.1:8000/api/v1/health | 后端自检（无需登录） | `status: ok`、`schema_version: 5` |
| http://127.0.0.1:8000/docs | FastAPI 接口文档 | 可展开接口列表 |

命令行检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-WebRequest http://127.0.0.1:5173/ -UseBasicParsing
```

### 4.2 最小使用流程

1. 打开 5173，注册一个账号并登录（没有默认账号）。
2. 进入“导入与分析”，上传 `csv/ptbxl_00001_lead_II_500Hz_10s.csv`，采样率填 **500**。
3. 等待任务从“排队”到“完成”，页面会自动进入记录详情。
4. 详情页可看质量、波形、分类/心率（取决于后端是否加载模型）、导出、备注、重分析、原件下载。
5. “合成回放”是 250 Hz、10 秒的演示信号；OpenECG 只接受 500 Hz，所以回放不会产生分类，这是正常的。
6. 历史页可筛选、看趋势、分页、删除；第二个账号授权后可只读查看。

### 4.3 模型是否加载

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health | Select-Object -ExpandProperty model
```

- `type: openecg`、`configured: true`：配置读到了；
- `loaded: null`：当前接口不主动加载模型，首次分析时才加载；
- 记录里出现 `未接入模型`：说明启动环境没装 `openecg`，或输入不是 500 Hz/10 秒。

## 5. 停止与重启

- **停止**：在两个窗口分别按 `Ctrl+C`；后端会收到中断并停止任务队列。
- **只重启后端**：改完后端代码或 `.env` 后，必须重启后端；前端页面刷新即可。
- **只重启前端**：Vite 通常热更新；改了 `vite.config.ts` 或依赖后重启。

如果窗口关了但端口还占着：

```powershell
# 先看是谁占用
Get-NetTCPConnection -LocalPort 8000 -State Listen |
  Select-Object LocalPort, OwningProcess

# 确认无误后结束该进程
Stop-Process -Id <上面的 OwningProcess> -Force
```

5173 被占用时同理换端口或结束旧的 node 进程。

## 6. 常见报错

| 现象 | 原因 | 处理 |
|---|---|---|
| `无法加载模块 ".venv-tasks"` | 当前目录不是仓库根目录 | `cd C:\Users\wsg\Desktop\health_system-v2` 再执行 |
| `cd frontend 找不到路径` | 不在仓库根目录 | 先 `cd` 到项目根，再进 `frontend` |
| `npm.ps1 ... 禁止运行脚本` | PowerShell 执行策略 | 用 `npm.cmd run dev`，或 `Set-ExecutionPolicy -Scope Process Bypass` |
| `[winerror 10048] 只允许使用一次` | 8000 已被旧后端占用 | 结束旧进程（见上一节），再启动 |
| Vite 报 `EBUSY ... watch ... tmpdir` | Windows 原子写临时目录触发文件监听 | 配置已改轮询；删除残留 `frontend/**/.*.tmpdir` 后重启；仍失败可换 Node 22 |
| 概览“时区无效” | 浏览器返回 `Etc/GMT-8` 等写法，旧后端不识别 | 已支持 `Etc/GMT±N`/`GMT±N`/`UTC±N`；**重启后端**生效 |
| 记录显示“未接入模型” | `.env` 写了 openecg，但启动环境没装 openecg | 改用 `.venv\Scripts\python.exe run_backend.py`，或把 requirements-ai 装进当前环境 |
| 控制台中文乱码 | Windows 代码页不是 UTF-8 | `chcp 65001` 后再启动；不影响功能 |
| pytest 报临时目录 `PermissionError` | 沙箱/权限限制 | 用 `-p no:cacheprovider`，测试已改用 `tests/.tmp` |

## 7. 测试、构建与备份

```powershell
# 后端测试
cd C:\Users\wsg\Desktop\health_system-v2
.venv-tasks\Scripts\python.exe -m pytest tests -q -p no:cacheprovider

# 前端类型检查 + 生产构建
cd frontend
npm.cmd run build

# 数据库备份（生成 runtime/backups/health-<时间戳>.sqlite3）
cd C:\Users\wsg\Desktop\health_system-v2
.venv\Scripts\python.exe business_logic\scripts\backup_db.py --keep 10
```

备份/恢复细节见[运维与备份](operations.md)。

## 8. 一句话速查

```powershell
# 后端（带模型）
cd C:\Users\wsg\Desktop\health_system-v2
.venv\Scripts\python.exe run_backend.py

# 前端
cd C:\Users\wsg\Desktop\health_system-v2\frontend
npm.cmd run dev

# 浏览器
# http://127.0.0.1:5173/
# 后端文档 http://127.0.0.1:8000/docs
```

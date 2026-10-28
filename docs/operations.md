# 运维与备份

依据[根 README](../README.md)与[记录与分析方案](plan/wangshuge-analyze-records-plan.md)，本文记录本机/单机部署的备份、恢复与审计保留操作。当前仍是单进程服务，不要配置多 worker 或多实例。

## 数据库备份

从仓库根目录执行：

```powershell
.venv-tasks\Scripts\python.exe business_logic\scripts\backup_db.py
```

默认写入 `runtime/backups/health-<UTC 时间戳>.sqlite3`，保留最近 10 份；脚本会重新打开备份并执行 `PRAGMA integrity_check`，同时打印记录数。可指定目录与保留数量：

```powershell
.venv-tasks\Scripts\python.exe business_logic\scripts\backup_db.py --target runtime\backups --keep 20
```

实现使用 sqlite3 的备份 API（不是直接复制正在写入的文件），因此在服务运行时执行也可得到一致快照。

## 恢复

1. 停止后端（结束 `run_backend.py` / uvicorn 进程），确保没有写入。
2. 把备份文件复制为 `runtime\health.sqlite3`。
3. 删除同目录下可能残留的 `health.sqlite3-wal`、`health.sqlite3-shm`，否则会与旧快照混用。
4. 启动后端，访问 `/api/v1/health` 确认 `database.writable=true` 与 `schema_version` 为当前版本。
5. 打开历史页抽查分页、详情、原件下载与趋势。

`runtime/uploads` 保存上传原件，与数据库分开；需要完整恢复时一并复制该目录。原件缺失不会影响记录本身，只是不能下载原件。

## 审计保留

访问审计写入 `record_access_log`，默认保留 90 天，启动时清理更早的记录：

```
ECG_AUDIT_RETENTION_DAYS=90   # 0 表示不清理
```

审计只保存记录 ID、操作者、动作与时间，不保存波形或备注内容；记录删除后审计仍保留，但接口只支持查询仍存在的记录，已删除记录的审计需要直接查 `record_access_log` 表。

## 迁移前备份

升级迁移会修改 `runtime/health.sqlite3`。升级前建议：

```powershell
Copy-Item runtime\health.sqlite3 runtime\health.sqlite3.bak-<日期>
```

迁移只在版本号前进时执行，已应用迁移的校验和变化会拒绝启动；不要手工修改已发布的迁移文件。

## 常见问题

- **数据库被占用**：确认没有第二个后端进程；SQLite 已启用 WAL 与 `busy_timeout=5000`，短暂并发会排队而不是立即失败。
- **时区统计不对**：接口接受 IANA 时区；Windows 未安装 `tzdata` 时中国时区按 +08:00 兜底，其他时区返回 400。
- **任务一直 pending/running**：当前为单进程队列；重启后 pending 会重新入队，running 会标为 `interrupted`。查看 `/api/v1/tasks/{id}?include_events=1` 的事件时间线。
- **记录完成但没有标签/心率**：说明后端没有加载模型（`/health` 中 `model.configured=true` 但 `loaded=null`）。确认启动用的虚拟环境安装了 requirements-ai.txt，用该环境的 python 执行 `import openecg` 自检；OpenECG 只接受 500 Hz、至少 10 秒的输入。换环境后对旧记录点“重新分析”即可。
- **备份文件越来越大**：波形已外置压缩；可清理旧备份，或按 `ECG_AUDIT_RETENTION_DAYS` 控制审计表。

# 当前接口契约

前缀 `/api/v1`；除 health 和 auth/register、auth/login 外，均需 `Authorization: Bearer <token>`。token 为数据库会话，不是原先固定密钥的演示 JWT。登录过期或退出后拒绝访问。

| 方法 | 路径 | 输入/用途 | 主责 |
|---|---|---|---|
| GET | /health | 运行状态、迁移版本、队列、模型配置与能力上限 | 王书阁 |
| POST | /auth/register | JSON username、password（至少8位） | 李运嘉 |
| POST | /auth/login | JSON username、password；返回 token | 李运嘉 |
| POST | /auth/logout | 注销当前 token | 李运嘉 |
| GET | /acquisition/status | 设备/回放状态 | 刘源 |
| POST | /acquisition/replay | 合成回放，HTTP 202 返回 Task | 刘源/王书阁 |
| POST | /analyze/ecg | multipart file（单列CSV，最大2MB）、sample_rate_hz；HTTP 202 返回 Task；支持 Idempotency-Key | 王书阁 |
| GET | /tasks | 本人任务分页列表，可按 `status` 过滤 | 王书阁 |
| GET | /tasks/{id} | 本人任务状态；`?include_events=1` 附事件时间线；完成后附 record | 王书阁 |
| POST | /tasks/{id}/cancel | pending 立即取消；running 协作取消 | 王书阁 |
| GET | /records | 本人记录；`shared=true` 为有效授权给我的记录；支持筛选与排序 | 王书阁 |
| GET | /records/trends | 按日趋势、汇总与时区 | 王书阁 |
| GET | /records/{id} | 本人/有效授权记录详情（波形从外置表重组） | 王书阁 |
| GET | /records/{id}/waveform | 时间窗 + 包络/均值降采样波形 | 王书阁 |
| GET | /records/{id}/raw | 本人下载原始上传 CSV | 王书阁 |
| GET | /records/{id}/access-log | 本人查询该记录的访问审计 | 王书阁 |
| POST | /records/{id}/reanalyze | 用已存输入重跑，HTTP 202 返回新 Task | 王书阁 |
| PATCH | /records/{id} | 本人备注（≤500 字符） | 王书阁 |
| GET | /records/{id}/export?format=csv\|json\|raw | 仅本人导出 | 王书阁 |
| DELETE | /records/{id} | 仅本人删除 | 王书阁 |
| GET | /analyze/{id} | 同一记录结果的兼容入口 | 王书阁 |
| GET/POST | /family/grants | 查询授权/JSON username 直接授权查看 | 李运嘉 |
| DELETE | /family/grants/{id} | 撤回本人发出的授权 | 李运嘉 |
| GET | /family/notifications | 有效授权关联的站内授权提示 | 李运嘉 |

## 错误语义

状态码：400 输入无效，401 未登录/会话失效，404 不存在或无权查看，409 状态冲突（任务已结束、缺少原始输入、用户已存在），413 上传超限，422 字段校验失败，503 数据库不可写。未知记录不返回假成功。

错误体保留字符串 `detail`，并新增 `code`、`request_id`（与响应头 `X-Request-ID` 一致）：

```json
{"detail": "记录不存在或没有查看权限", "code": "record_not_found", "request_id": "b1c0e6f2", "field": null}
```

常见 `code`：`invalid_request`、`auth_required`、`not_found`、`record_not_found`、`task_not_found`、`task_finished`、`input_unavailable`、`payload_too_large`。

## 分析任务

- 上传与回放返回 HTTP 202 + Task；同一 `Idempotency-Key`（≤64 字符）重复提交返回原任务并置 HTTP 200。当前不做过期清理，键会一直保留。
- Task 字段：`id`、`status`、`stage`、`outcome`、`error`、`error_code`、`record_id`、`source`、`created_at`、`updated_at`、`started_at`、`finished_at`、`cancel_requested`、`processing_version`、`source_record_id`、`duration_ms`；完成后附 `record`。
- `status`：pending / running / completed / failed / cancelled；`completed` 只表示流水线结束，是否产生分类看 `outcome`（classified / skipped_quality / model_unavailable / unknown）。
- `stage`：queued / validating / preprocessing / inference / explaining / finished。
- `error_code`：input_invalid / analysis_failed / interrupted / cancelled。前端据此给“换文件/重试/重新提交”建议。
- 取消：pending 直接 cancelled；running 置 `cancel_requested=true`，在阶段边界生效，模型调用中不强制中断；已结束返回 409 `task_finished`。
- 后台为进程内单 worker 队列（FastAPI lifespan 启动），支持心跳与租约字段；重启后 pending 重新入队，running 任务一律标为 `interrupted`（当前仅支持单进程）。不支持多进程/多实例。
- 上传原件保存在 `runtime/uploads/<owner>/<task>.csv`，任务与记录通过 `input_path` 关联；写盘失败不阻塞分析，只是不能下载原件。
- `GET /tasks/{id}?include_events=1` 返回 `events`：`id`、`status`、`stage`、`error_code`、`detail`、`created_at`，按发生顺序排列，用于解释排队、失败或取消过程。

## 记录查询

- GET /records 参数：`shared`、`page`（≥1）、`page_size`（1–100，默认 20）、`from`、`to`（YYYY-MM-DD 或 ISO，含当日）、`quality`（basic_checks_passed/insufficient/unknown）、`label`、`q`（ID 前缀或备注，≤80）、`sort`（created_at_desc/created_at_asc）。
- 不传 `page` 仍返回数组（兼容旧调用），数组项已带摘要字段；传 `page` 返回 `items/page/page_size/total/pages/shared`。
- 列表项：`id`、`created_at`、`updated_at`、`task_id`、`source`、`lead`、`unit`、`sample_rate_hz`、`duration_sec`、`n_samples`、`quality_status`、`quality_score`、`label`、`confidence`、`heart_rate_bpm`、`model_version`、`processing_version`、`note`、`supersedes_record_id`；共享视图额外 `owner_username`。
- 详情在结果 JSON 之外补充摘要字段、`owner_username`、`owned`、`has_raw_file`。波形不在结果 JSON 中重复存储，读取时从 `record_signals` 解压重组，接口形状与旧版一致。
- 趋势：`GET /records/trends?days=1..365&timezone=IANA&fill=1|0&shared=`，返回 `days_requested/timezone/shared/summary/days`。`summary` 含 total、classified、insufficient、heart_rate_days、avg_heart_rate_bpm、last_record_at；每日含记录数、质量计数、心率均值/最小/最大值。默认时区 UTC；前端显式传浏览器时区。除 IANA 名称外也接受 `Etc/GMT±N`、`GMT±N`/`UTC±N`（`Etc/GMT-8` 表示 UTC+8，与常见写法相反）；无 tzdata 时常见中国时区按 +08:00 兜底，其他名称报 400 `invalid_request`。

## 波形窗口

`GET /records/{id}/waveform?start_sec=0&end_sec=10&max_points=2000&mode=envelope|mean`

- 权限与详情一致：本人或有效授权可读。
- `max_points` 100–8000（默认 2000）；`envelope` 每桶保留极值两点，`mean` 每桶均值，避免抽点漏掉尖峰。
- 响应：`record_id`、`sample_rate_hz`、`unit`、`total_samples`、`start_sec`、`end_sec`、`returned_points`、`mode`、`points[{t,v}]`。
- 无波形数据返回 409 `input_unavailable`；时间窗无效返回 400 `invalid_request`。

## 原件、重分析、备注

- `GET /records/{id}/raw`：仅本人；返回原始上传字节，文件名固定为 `ecg-record-<id>-raw.csv`，不反射用户文件名。无原件或已清理返回 409 `input_unavailable`。
- `POST /records/{id}/reanalyze`：仅本人；优先复用保存的标准输入，生成**新任务和新记录**，新记录通过 `supersedes_record_id` 指向原记录，原记录保留。原始输入已被清理返回 409。共享只读用户 404。
- `PATCH /records/{id}`：仅本人；JSON `{"note": "..."}`，最多 500 字符，空串清除；未知字段 422；共享只读用户 404。备注同步出现在详情、列表、JSON 导出。
- 导出：CSV 带 UTF-8 BOM，列为 timestamp_sec/value/sample_rate_hz/unit/source/quality_status/quality_reasons/heart_rate_bpm/record_id/created_at；JSON 为完整记录对象；`raw` 等同于原件下载。均只限本人。
- 删除：仅本人；同一事务清理记录、关联任务、任务输入、任务事件与波形，提交后删除原件文件；若其他记录通过 `supersedes_record_id` 指向它，会先置空该字段，避免删除失败。未知或无权限均为 404。

## 访问审计

详情、波形、原件、导出、备注、重分析、删除会写入 `record_access_log`（记录 ID、操作者、动作、时间），不保存波形或备注内容；记录删除后审计保留。

`GET /records/{id}/access-log?action=&page=1&page_size=20`：仅记录本人可查；按时间倒序返回 `record_id`、`items`（`id`、`action`、`detail`、`created_at`、`actor_id`、`actor_username`）、`page/page_size/total/pages`。`action` 仅支持 view/waveform/raw/export/note/reanalyze/delete，其他值 400。共享只读用户 404。记录删除后审计仍保留，但当前没有按已删除记录查询的接口，需要直接查库。

审计默认保留 90 天（`ECG_AUDIT_RETENTION_DAYS`，0 表示不清理），启动时清理更早记录。备份、恢复与保留操作见[运维与备份](../docs/operations.md)。

## 健康检查

`GET /health` 无需登录，返回 `status`、`version`、`database`（writable、schema_version）、`tasks`（mode/workers/pending/running）、`model`（type/configured/loaded，`loaded=null` 表示未探测）、`acquisition`、`capabilities`（上传格式、大小、样本上限、波形点数、时区支持）。数据库不可写时返回 503。不加载模型、不泄露绝对路径。

## WebSocket 与未实现能力

WebSocket `/api/v1/ws/realtime` 尚未实现，主动关闭，不发送模拟分析。

通知仅为站内授权提示，状态 in_app_available 不代表外部渠道投递或急救警报。授权原型为本人直接共享，不包含接收方确认；家属导出权限待团队确认，当前默认拒绝。审计查询接口、软删除与保留策略、备份恢复接口为后续阶段。

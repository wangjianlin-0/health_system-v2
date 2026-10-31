# 数据与模块契约

标准 AI 输入仍为 `samples`（ECG mV）、`sample_rate_hz`、`unit=mV`、`lead`、`source`。ADS1292R 适配器额外接收每帧 `status_word + ch1 + ch2`：24 位通道按二补码解码，默认 `CH1=respiration`、`CH2=ecg`，随后生成 `respiration_samples`、`hardware_status`、`channel_mapping` 和标定元数据。CSV 支持单列 mV、`status_word/ch1/ch2` 原始帧列，或 `ecg_filtered/resp_filtered` 命名列。

`process(signal)` 返回 ECG `waveform`，并在双通道输入时返回 `respiration_waveform`、`respiration`、`hardware_status` 和 `channel_mapping`。呼吸率是相对阻抗波形的工程估计；没有板级标定时单位保持 `adc_count`，不得标为欧姆。

`analyze(signal)` 是软件唯一分析入口。状态字异常或 ECG 导联脱落会进入质量门控并跳过分类；ECG 波形只发送给 ECG 分类器，呼吸波形不会送入 OpenECG/ECGFounder。prediction 含 status、label、confidence、model_version、explanation；默认无分类器时不伪造正常/异常结论。

## 数据库与迁移

权威 schema 由 `business_logic/db/migrations/` 下的版本化迁移维护，`storage.initialize()` 按版本应用并写 `schema_migrations(version, name, checksum, applied_at)`；已应用迁移的校验和变化会拒绝启动。禁止再回到“只写 CREATE TABLE IF NOT EXISTS”的隐式建表。连接启用 WAL、`busy_timeout=5000` 与外键。

表：`users`、`sessions`、`records`、`record_signals`、`record_access_log`、`analysis_tasks`、`task_inputs`、`task_events`、`grants`、`notifications`、`schema_migrations`。用户/会话/授权的字段语义由账户模块维护；本契约只描述记录与任务侧新增字段。

### records

`id`、`owner_id`、`created_at`（UTC ISO）、`payload`（结果 JSON，**不含 waveform**）+ 摘要列：

`task_id`、`source`、`lead`、`unit`、`sample_rate_hz`、`duration_sec`、`n_samples`、`quality_status`、`quality_score`、`label`、`confidence`、`heart_rate_bpm`、`model_version`、`processing_version`、`note`、`input_path`、`input_sha256`、`supersedes_record_id`、`updated_at`。

摘要列由 `analyze()` 结果在同一事务写入；列表、筛选、趋势只读摘要列，详情才解析 `payload`。索引：`(owner_id, created_at)`、`(owner_id, quality_status, created_at)`、`task_id`。

### record_signals

`record_id`（主键，外键到 records，ON DELETE CASCADE）、`sample_rate_hz`、`unit`、`n_samples`、`encoding`（当前 `f32le+zlib`）、`data`（压缩后的 float32 字节）。波形在保存时从结果中剥离，读取时由 `detail`/波形接口解压重组，对外结构不变。编码实现见 `business_logic/app/services/signals.py`。

### analysis_tasks / task_inputs / task_events

`analysis_tasks` 在原有字段外增加：`stage`、`source`、`outcome`、`error_code`、`worker_id`、`started_at`、`finished_at`、`heartbeat_at`、`cancel_requested`、`attempt`、`input_sha256`、`idempotency_key`、`source_record_id`、`input_path`。唯一索引 `(owner_id, idempotency_key)` 保证幂等。

`task_inputs` 保存标准输入 JSON，供重启恢复与后续重分析。`task_events` 记录 pending/running/completed/failed/cancelled 迁移与错误码，用于追溯“为什么失败”。上传原件保存在 `input_path` 指向的 `runtime/uploads/<owner>/<task>.csv`，写盘失败不阻塞分析。

## 记录输出

Record：`id`、`created_at`、`task_id`、`task_status`、`result`，列表/详情补充摘要字段；`owner_username` 为所有者用户名，`owned=false` 表示共享只读，`has_raw_file` 表示原件是否可下载。`result` 结构与旧版一致，`waveform` 由 `record_signals` 在读取时重组。

趋势输出：`days_requested`、`timezone`、`shared`、`summary`（总数、分类数、质量不足数、有心率日期数、平均心率、最后记录时间）、`days`（UTC 或指定时区按日聚合：records、quality 计数、classified、心率均值/最小/最大）。`timezone` 支持 IANA 名称与 `Etc/GMT±N`、`GMT±N`/`UTC±N` 偏移写法（`Etc/GMT-8` = UTC+8）。只统计已保存结果，不是疾病风险预测。

## 权限与删除

记录 owner_id 与会话 user_id 关联；共享查询必须匹配有效授权（`grants.active=1`）。撤回限制后续查询，不能抹除已被查看或下载的副本。导出与删除仅限本人；共享视图只读。

删除在同一事务清理 `task_inputs`、`analysis_tasks`、`task_events`（外键级联）、`record_signals` 与记录，事务提交后删除原件文件；若其他记录或任务通过 `supersedes_record_id`/`source_record_id` 指向它，会先置空这些字段再删除。`record_access_log` 保留动作元数据（记录 ID、操作者、动作、时间），不保存波形或备注内容。

## 访问审计

`record_access_log`：`id`、`record_id`（不做外键，记录删除后保留）、`actor_id`、`action`（view/waveform/raw/export/note/reanalyze/delete）、`detail`、`created_at`。仅记录本人可通过 `GET /records/{id}/access-log` 查询，按时间倒序分页；默认保留 90 天，启动时清理更早记录（`ECG_AUDIT_RETENTION_DAYS`）。

## 可选流水线输出

依据[根 README](../README.md)，默认模型不可用；现有代码可附加 prediction.evidence 和 prediction.explanation_detail。可选分类器可能增加 raw_label、task_type、heart_rate、beats、intervals_ms、flags；这些字段不表示真实推理已验收，也不会填充顶层 heart_rate_bpm。解释默认模板，可选外部生成失败回退模板。

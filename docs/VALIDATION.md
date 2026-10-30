# 验证记录

## 历史验证（2026-10-20）

以下为此前记录，不代表当前新增测试全部通过。

- `python -m pytest tests -q`：4 项通过。包括两用户身份隔离、记录持久化、共享查询、授权撤回、退出令牌失效、CSV 单列/非有限/采样率/超限校验、未知记录查询、真实预测评价计算。
- `npm run build`：TypeScript 检查与 Vite 生产构建通过。配置使用 runner，避免当前 Windows 沙箱的原生配置打包器目录读取问题。
- 未验证：真实设备、真实数据集上的正式质量算法、模型性能、外部通知、Docker 运行、生产并发与部署。
- 原模型评价固定指标已移除，不以此测试结果宣称模型效果。

本记录对应本次框架实现；后续功能变化需由模块作者更新证据。

## 本轮文档与实现审查（2026-10-21）

以根 README 为说明依据，审查仓库全部 27 份 Markdown；仅修改说明，保留代码框架、目录和接口实现。分工按业务线同时覆盖页面与接口，统一默认功能、待实现能力与条件扩展。

### 验证结果

- frontend 中 npm run build：TypeScript 与 Vite 构建通过。
- 27 份 Markdown 的本地链接、代码围栏及 git diff --check 检查通过。
- .venv/Scripts/python.exe 无法创建解释器进程；系统 Python 执行 python -m pytest tests -q 报 No module named pytest，因此本轮后端全套测试未运行，不沿用历史“4 项通过”作为当前结果。
- 直接执行当前 parse_csv 的多列硬件样例，已确认触发单列限制；新增 test_hardware_csv_uses_filtered_ecg_column 却期望提取 ecg_filtered，测试与实现冲突。
- Docker、真实设备、真实数据正式处理、可选分类器实际加载、外部解释服务和生产并发均未验收。

### 未改代码的问题

| 问题 | 影响与后续负责人 |
|---|---|
| 多列硬件 CSV 测试与解析不一致 | 信号模块与硬件模块确认格式；当前不能宣称支持硬件 CSV 上传 |
| 同步任务仅保存成功记录 | 记录模块补持久化状态、异步执行和重启恢复 |
| health 固定 model=unavailable | 可选模型状态无法由健康接口确认，记录模块与模型模块对接 |
| 分类器首次初始化失败后缓存不可用 | 修复配置/依赖后需重启，模型模块完善诊断 |
| OpenECG 将采样率取整、只分析前 10 秒 | 模型模块验证精确输入要求与窗口追溯，不能声称全记录分析 |
| 可选分类器未知原标签默认映射 other_abnormality | 模型模块核实标签契约和未知输出语义 |
| 外部解释返回值缺少严格结构与事实校验 | 模型模块验证内容、字段类型和证据一致性；模板补字段不能代替校验 |
| 页面固定心率未实现、不展示完整解释对象 | 记录模块后续联调；顶层 heart_rate_bpm 当前仍为 null |
| 缺少分页/趋势/导出删除、邀请确认和外部推送 | 按根 README 分别由两位软件负责人推进 |

### 文档修正

纠正旧 STM32/固定采样参数、双模型主备与熔断、Python/C 双版本截止日期、固定指标目标、无效评价/校验命令、后端启动目录和 WebSocket 完整路径。可选 OpenECG/解释代码单独标注为未完成真实验收。未修改用户已有 test_ecg_normal.csv。

## 本地任务阶段实现（2026-10-21，后续更新）

新建 .venv-tasks 并安装 requirements-dev.txt，保留旧环境。实现 analysis_tasks/task_inputs，上传与合成回放返回 202，后台更新状态并原子保存结果；GET /tasks/{id} 仅限任务本人；启动时遗留 pending/running 标为失败并提示重新提交。重复执行同一任务不重复保存记录。前端通过 URL task 参数刷新恢复轮询，完成后跳转详情，失败显示原因。

使用 FastAPI BackgroundTasks，仅用于单进程本地服务，不支持多 worker/多实例，也不是独立持久化消费队列；没有自动重试。分页/趋势/导出删除仍待后续阶段。

验证：任务/API 专项 6 项通过，覆盖待执行任务、成功回看、失败原因、未知任务、用户隔离、授权撤回、重启遗留状态、重复执行。前端 TypeScript/Vite 构建通过。此前已知多列硬件 CSV 测试失败未修改算法或隐藏测试。

## 历史管理阶段（2026-10-21）

完成 SQL 分页、UTC 日趋势、本人 CSV/JSON 导出与事务删除，历史页提供分页、范围选择、导出和删除确认，Dashboard 展示近 30 天记录概览。保持不传 page 的旧数组查询兼容。删除关联标准输入与任务，不保留可重新访问的副本。

业务 API 测试 7 项通过，新增覆盖跨页查询、分页参数、缺失心率、导出格式、家属导出/删除拒绝及删除后任务/记录不可访问。前端构建通过；未完成浏览器人工视觉验收。此前硬件多列 CSV 测试与解析冲突仍待信号模块/硬件模块处理。

## 发布前目录与依赖整理（2026-10-24）

- 将误放在 csv/ 的 conftest.py、test_ai_pipeline.py、test_api_flow.py 恢复到 tests/，保留原测试内容；CI 继续执行 python -m pytest tests -q。
- 修复硬件 CSV 的 ecg_filtered 列提取，以及分类工厂从项目根 .env 读取 ECG_MODEL_TYPE；进程环境变量优先。
- 增加模型配置回归测试，隔离本机模型缓存与远程解释配置。后端全量测试 14 项通过；前端 npm run build 通过。
- 可选模型依赖固定 openecg[report]==0.11.0；虚拟环境、权重、缓存、账号数据库、真实密钥不上传。
- 发布 PTB-XL v1.0.3 公开 II 导联 CSV、来源 JSON 和 CC BY 4.0 许可：500 Hz、5000 点、10 秒，无重采样或重复信号。该样本已完成网站 API 联调；不表示模型临床性能已验收。
- 旧版审查记录保留当时日期与边界；本节是后续更新。外部解释仍默认本地模板，真实硬件单位与模型未知标签映射等待验收事项不在本次整理范围内。

## 记录与分析 P0（2026-10-28）

按[记录与分析完善方案](plan/analyze-records-plan.md)实施 P0：

- 数据库：新增 `schema_migrations` 与 0001–0003 迁移；`records` 增加摘要列、索引并用 JSON1 回填；`analysis_tasks` 增加 stage/heartbeat/error_code/幂等键等字段与 `task_events`；连接启用 WAL 与 `busy_timeout`。
- 任务：进程内单 worker 队列替换 BackgroundTasks；原子认领、心跳与租约、取消（pending 立即取消，running 协作取消）、幂等键、启动恢复（pending 重新入队，running 超时标 interrupted）。
- 接口：新增 `GET /tasks`、`POST /tasks/{id}/cancel`；`/records` 支持筛选/排序并返回摘要字段；`/records/trends` 支持 `timezone`、零填充与 summary；错误体新增 `code`/`request_id`；`/health` 报告迁移版本、队列与能力上限。
- 页面：Analyze 拆为上传/任务进度/详情组件，加入本地预检、上传进度、退避轮询、取消与元数据表；Records 支持筛选进 URL、汇总卡、SVG 趋势图与共享只读标识；Dashboard 加入进行中任务与最近记录；波形改为按桶保留极值的降采样。

验证：

- 后端 `python -m pytest tests -q -p no:cacheprovider`：33 项通过（上一轮 14 项，本轮新增 19 项，覆盖迁移回填与校验、任务列表/取消/恢复/幂等、筛选与趋势时区、健康检查、错误体、多 worker 守卫）。
- 前端 `npm run build`：TypeScript 与 Vite 生产构建通过（45 个模块）。本机在 DSH 沙箱下 Vite 读取配置触发 `spawn EPERM`，按工具约束对同一条构建命令申请一次更宽权限后完成，未修改构建配置。
- 本机缺少 tzdata，`Asia/Shanghai` 使用固定 +08:00 兜底并通过边界用例；`business_logic/requirements.txt` 已加入 tzdata（dev 通过 `-r` 继承），装齐后走真实时区库。
- 测试临时目录：沙箱拒绝 pytest 默认临时根，`tests/conftest.py` 改用 `tests/.tmp/<uuid>`（已加入 .gitignore）。

未验证：真实浏览器人工验收、真实设备与模型、多进程部署；重分析、原始文件、波形窗口、备注与访问审计属于 P1，尚未实现。当前仍为单进程任务队列，不要配置多 worker。

## 记录与分析 P1（2026-10-28）

- 迁移 0004：新增 `record_signals`，把历史记录 payload 中的 waveform 转成 zlib + float32 外置，payload 只保留结果；读取时由 `detail` 解压重组，接口形状不变。迁移 0005：任务 `input_path` 与 `record_access_log`。
- 接口：`GET /records/{id}/waveform`（时间窗、envelope/mean、100–8000 点）、`GET /records/{id}/raw`、`POST /records/{id}/reanalyze`、`PATCH /records/{id}` 备注、`export?format=raw`；详情新增 `has_raw_file`，删除级联波形与原件，访问动作写审计。
- 页面：详情页加入下载原件、重新分析、备注编辑与重分析来源链接；原件/备注仅本人可操作，共享视图只读。

验证：

- 后端 38 项通过（P0 的 33 项 + 5 项 P1：波形窗口/共享权限、原件下载、重分析链、备注权限、审计与删除级联）。
- 前端 `npm run build` 通过（45 个模块，dist JS 200.9 KB）。
- 真实库升级到 schema v5：16 条记录、16 条波形行；payload 合计约 30 KB，外置压缩波形约 185 KB；详情解压出 2500 点，窗口接口 1 秒返回 167 点。
- 测试上传目录已隔离到临时目录，避免在 `runtime/uploads` 残留测试文件。

未验证：浏览器人工验收；波形窗口的前端缩放/拖动交互（接口已就绪，UI 仍用本地降采样）；审计查询接口；P2 的软删除、备份恢复、样例下载。真实设备、模型效果与多进程仍未验收。

## 记录与分析 P2（2026-10-28）

- 任务事件：`GET /tasks/{id}?include_events=1` 返回 pending/running/failed 等事件与错误码；不传参数保持旧响应。
- 审计查询：`GET /records/{id}/access-log` 仅本人可查，支持 action 过滤与分页；审计默认保留 90 天，启动时清理更早记录（`ECG_AUDIT_RETENTION_DAYS`）。
- 备份：新增 `app/services/backup.py` 与 `business_logic/scripts/backup_db.py`，使用 sqlite3 备份 API，写入 `runtime/backups/health-<时间戳>.sqlite3`，校验完整性并保留最近 N 份；[运维与备份](operations.md)记录恢复步骤。
- 页面：详情页波形支持按时间窗调用 `/records/{id}/waveform` 查看局部包络并可恢复全览；历史页支持每页 10/20/50；补充打印样式。

验证：

- 后端 42 项通过（P1 的 38 项 + 4 项 P2：任务事件、审计查询与过滤、保留清理、备份与保留策略）。
- 前端 `npm run build` 通过（45 个模块，dist JS 203.0 KB）。
- 备份函数在测试库上连续生成 3 份并只保留 2 份，备份文件 `integrity_check=ok` 且记录数可读。

未验证/未完成：真实浏览器人工验收；软删除与更细的保留策略；公开样例下载入口；前端自动化测试（无 vitest 依赖）；审计查询本身的页面（当前只有接口）。

## 现场问题修复（2026-10-28 浏览器验收）

- 概览报“时区无效”：浏览器返回 `Etc/GMT-8`，原逻辑只识别 UTC/GMT/Z 与部分中国 IANA 名称。现在支持 `Etc/GMT±N`、`GMT±N`/`UTC±N` 固定偏移（`Etc/GMT-8` 表示 UTC+8），并增加趋势边界用例。
- 详情提示“无法给出明确辅助分类，请重新测量”：当 `prediction.status=model_unavailable` 时，模板解释被误当成“结果不确定”。页面改为单独说明“只完成信号检查”，列出常见原因（未装模型依赖，或输入不满足 500 Hz、10 秒）并隐藏不适用的一般解读；`skipped_quality` 仍提示质量不足。
- 现场核对：用户记录 quality=basic_checks_passed、prediction.status=model_unavailable；`.venv-tasks` 未安装 openecg，而 `.env` 写的是 openecg，因此降级为无模型。改用 `.venv` 启动后，同一 PTB-XL 500 Hz 样本得到 classified / normal / 置信度 1.0 / 心率 64 / 11 拍，约 1.5 秒完成。
- 验证：后端 42 项通过；前端构建通过（45 modules，203.66 KB JS）。

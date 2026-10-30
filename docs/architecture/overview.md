# 原链路分析与重构设计

总体说明依据[根 README](../../README.md)；本页原仓库问题为历史背景，不能当作当前实现现状。

## 原仓库的链路与断点

原本计划：STM32/上传 → FastAPI → 信号处理 → AI → React/历史。

实际源码中：App 没有挂载页面；FastAPI 没挂载路由；分析后台函数 pass；结果和实时接口返回固定正常/心率；records 返回空列表；信号和推理函数 pass；评价脚本固定指标。目录齐全但数据链路未接通。原分工把页面、全部 API、数据库与集成都交给一个人，业务责任集中。

## 改造后的可执行结构

```text
frontend/src/pages/Login、Family ── auth/family API ── services/family（账户模块）
                                              │ 身份、有效授权
frontend/src/pages/Analyze、Records ── analyze API ── services/records（记录模块）
                                                    │
hardware/acquisition（硬件模块，回放/未来设备） ── 标准输入  │
signal_processing/python（信号模块，CSV/质量） ────────┤
                                                    ▼
ai_model/pipeline（模型模块） → process → 质量判断 → inference/factory
                                                    │
                                  records 保存结果 → SQLite → 页面回看
```

保留主要目录，而非把另一套标准库 HTTP 应用放进原项目。两位软件成员各自承担页面和 API，分析流水线集成从软件层移到 ai_model/pipeline。采集回放与未来设备使用相同输入协议。

## 状态与边界

- 任务框架：上传/回放返回 202 与 pending 任务；后台更新 running/completed/failed。文件格式错误直接拒绝，分析错误写入任务。重启后未完成任务标为 failed，提示重新提交。
- 质量状态 independent：insufficient/basic_checks_passed；基础检查不等于完整信号质量判定。
- 没模型返回 model_unavailable 和空标签；质量不足返回 skipped_quality；不输出固定正常/置信度。
- 授权与身份每次由后端检查，session 存数据库，退出后失效；仅本地开发使用。
- 暂不启动自动实时连接；未实现的 WebSocket 显式拒绝。

## 与原目录的兼容及清理

沿用 frontend、business_logic、hardware、signal_processing、ai_model、data、interfaces、docs。原 C 头文件、固件草案和模型扩展配置保留作参考。新增忽略规则，后续依赖通过清单重装；上游已跟踪的 node_modules/pyc 留作历史，建议下一次仓库维护时移出跟踪。原固定指标脚本改为根据传入真实预测计算指标。

数据库权威结构在 business_logic/app/services/storage.py，init.sql 指向该来源，避免双份 schema。Docker 构建上下文改为仓库根目录，以便导入跨领域模块。旧中间件和 config.py 为未挂载参考，不是当前安全或追踪能力的证明。

## 2026-10-21 审查补充

流水线已包含可选 OpenECG 与 evidence/解释模块；默认无分类器，不表示真实模型已验收。现有采集 CSV 测试与单列解析实现冲突。WebSocket 实际完整路径为 /api/v1/ws/realtime。完整审查及验证限制见[验证记录](../VALIDATION.md)。

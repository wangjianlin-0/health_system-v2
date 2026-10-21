# 当前接口契约

前缀 `/api/v1`；除 health 和 auth/register、auth/login 外，均需 `Authorization: Bearer <token>`。token 为数据库会话，不是原先固定密钥的演示 JWT。登录过期或退出后拒绝访问。

| 方法 | 路径 | 输入/用途 | 主责 |
|---|---|---|---|
| GET | /health | 运行状态与尚未接入能力 | 王书阁 |
| POST | /auth/register | JSON username、password（至少8位） | 李运嘉 |
| POST | /auth/login | JSON username、password；返回 token | 李运嘉 |
| POST | /auth/logout | 注销当前 token | 李运嘉 |
| GET | /auth/session | 当前用户名及会话过期时间 | 李运嘉 |
| GET | /acquisition/status | 设备/回放状态 | 刘源 |
| POST | /acquisition/replay | 合成回放，返回已保存 Record | 刘源/王书阁 |
| POST | /analyze/ecg | multipart file（单列CSV，最大2MB）、sample_rate_hz（50–2000） | 王书阁 |
| GET | /records | 本人记录；shared=true 为有效授权给我的记录 | 王书阁 |
| GET | /records/{id} | 本人/有效授权记录详情 | 王书阁 |
| GET | /analyze/{id} | 同一记录结果的兼容入口 | 王书阁 |
| GET/POST | /family/grants | 查询本人发出的邀请与授权/发送待确认邀请 | 李运嘉 |
| PATCH | /family/grants/{id} | 调整 records:list、records:read 权限范围 | 李运嘉 |
| DELETE | /family/grants/{id} | 撤回本人发出的邀请或授权 | 李运嘉 |
| GET | /family/invitations | 查询发给当前用户的邀请 | 李运嘉 |
| POST | /family/invitations/{id}/accept | 接受邀请并激活授权 | 李运嘉 |
| POST | /family/invitations/{id}/decline | 拒绝邀请 | 李运嘉 |
| GET | /family/notifications | 查询站内通知历史 | 李运嘉 |
| PATCH | /family/notifications/{id} | 标记通知 read 或 dismissed | 李运嘉 |

状态：400 输入无效，401 未登录/会话失效，404 不存在或无权查看，409 用户已存在，413 上传超限，422 字段校验失败。错误响应使用 detail；框架默认校验错误可能为结构化列表。未知记录不返回假成功。

WebSocket `/ws/realtime` 尚未实现，主动关闭，不发送模拟分析。

新邀请默认 pending，接收方接受后才激活。`records:list` 仅允许查看共享记录列表，`records:read` 同时允许查看详情且会自动包含列表权限。通知状态为 unread、read 或 dismissed，仅代表站内状态，不代表外部渠道投递或急救警报。重构前 OAuth 表单及强制心律结果契约不再适用。

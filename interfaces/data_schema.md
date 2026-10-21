# 数据与模块契约

首版输入：samples（单通道数值数组）、sample_rate_hz、unit=mV、lead、source。CSV 为单列数值，可含 value/sample/mv 表头；其他列必须拒绝以免把时间列当信号。合成输入 source=synthetic_replay。后续设备增加 captured_at、sequence 和缺失标记。

`process(signal)` 返回 quality、waveform、sample_rate_hz、unit、duration_sec、heart_rate_bpm=null、processing_version。quality 包含 status、reasons、scope；目前只做长度/平直/有限值检查。

`analyze(signal)` 是软件唯一分析入口，附加 source、mode=framework_demo、prediction。prediction 含 status、label、confidence、model_version、explanation。模型不可用时后三个值为空；低质量跳过分类。心拍标签与记录级心律结论不能混用。

Record：id、created_at（UTC ISO）、task_status、result。当前同步执行，completed 代表流水线结束，不表示模型已有输出。后续模型还需标签版本、配置、输入来源追溯和窗口位置。

用户/会话/记录/授权/通知表由 `business_logic/app/services/storage.py` 初始化。会话记录服务端过期时间；过期或退出后令牌失效。家庭邀请状态为 pending、accepted、declined 或 revoked，只有 accepted 且 active 的授权生效。权限包含 `records:list` 和 `records:read`；后者自动包含前者。记录 owner_id 与会话 user_id 关联，共享列表和详情分别核验对应权限。撤回限制后续查询，不能抹除已被查看或下载的副本。通知保留历史并记录 unread、read、dismissed 状态。

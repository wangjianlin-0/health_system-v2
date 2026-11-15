# 课程迁移说明

原项目：https://github.com/lykzr/ecg-edge-analysis

原提交：d83c05616c7d09c3de2aa34d40b1a8042bad0b12。

`model/inference`、`model/cnn_fourclass`、`src/reference/ecg_trainable_cnn.py` 从原项目按原字节复制，保留 MIT、WFDB 和原模型来源说明。新增的 `migration_manifest.json` 对每个复制文件计算 SHA256，启动模型进程时验证。模型本身未修改、未训练。网络定义依赖的原目录结构在此目录内保留。

应用适配、整段前缀预览、认证串口接口、记录持久化位于课程项目自身代码中，见 `docs/PC_MIGRATION.md`。vendor 中保留的训练、准备与历史检查脚本用于原始研究的追溯，其原数据库和完整原项目依赖未一并复制；课程运行及验证请使用顶层 `scripts/check_pc_models.py`，无需执行训练脚本。

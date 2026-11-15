# 自动测试

本目录保留全部 pytest 脚本及 conftest.py，GitHub Actions 从仓库根目录执行 python -m pytest tests -q。

- test_ai_pipeline.py：证据、解释模板和硬件 CSV 解析。
- test_api_flow.py：认证、授权、任务、重启恢复、历史、导出和删除。
- test_model_configuration.py：项目 .env 配置、环境变量优先级和默认不可用行为。

conftest.py 通过 monkeypatch 隔离本机模型配置、分类器缓存和远程解释，测试运行不下载模型、不调用远程 API，不修改真实运行数据库。

可上传的公开数据放在 ../csv/，不要将 Python 测试文件移动到该目录。

## 电脑迁移验收补充（2026-11-12）

`test_pc_migration.py` 验证蓝牙协议、模拟串口、权限、保存和模型选择；`test_pc_models_integration.py` 与 `test_pc_preview.py` 使用随仓库冻结模型和合成数据进行实际CPU推理，无需联网、训练或连接硬件。请用共享PyTorch环境运行完整测试：

```powershell
E:/Environments/Python/pytorch/Scripts/python.exe -m pytest tests -q
```

原有不接模型测试仍由conftest隔离配置。模型数值检查另执行 `scripts/check_pc_models.py`。

基础CI若未安装torch会跳过两项真实CNN测试；完整验收必须使用上方PyTorch环境，确认无跳过。无PyTorch的Linux CI还需重建vendor原生检测程序才可运行完整模型测试。

# 自动测试

本目录保留全部 pytest 脚本及 conftest.py，GitHub Actions 从仓库根目录执行 python -m pytest tests -q。

- test_ai_pipeline.py：证据、解释模板和硬件 CSV 解析。
- test_api_flow.py：认证、授权、任务、重启恢复、历史、导出和删除。
- test_model_configuration.py：项目 .env 配置、环境变量优先级和默认不可用行为。

conftest.py 通过 monkeypatch 隔离本机模型配置、分类器缓存和远程解释，测试运行不下载模型、不调用远程 API，不修改真实运行数据库。

可上传的公开数据放在 ../csv/，不要将 Python 测试文件移动到该目录。

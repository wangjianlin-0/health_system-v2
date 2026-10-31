# FastAPI 业务与持久化

记录模块：应用入口、记录/任务服务、存储；账户模块：身份/授权/通知 API 与服务；硬件模块：acquisition 适配接口。分析通过 ai_model.pipeline 调用，业务层不重复实现信号和模型算法。

依据[根 README](../README.md)，从仓库根目录运行 `python run_backend.py`。本目录 requirements.txt 是当前运行依赖；旧 config/middleware 仅保留参考，未自动启用。db/init.sql 指向唯一 schema 定义。Docker 说明见 deploy/deploy_backend.md。

当前上传/回放创建持久化任务并后台执行，查询 /tasks/{id} 仅限本人。重启后 pending/running 任务标为 failed，保留输入并提示重新提交。已支持分页、趋势和本人导出/删除。默认 health 的 model 字段固定 unavailable，不是可选分类器的实时健康探测。

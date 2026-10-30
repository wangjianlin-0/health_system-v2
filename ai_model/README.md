# 模型模块：AI 算法与分析集成

pipeline.py 是统一入口，调用信号模块的 process 后判断质量，再调用 inference/factory。默认 ECG_MODEL_TYPE=none，返回空分类与 model_unavailable，不输出模拟正常结果；不能将可选适配代码视为已加载模型。

下一步：单导联任务标签、患者级划分、基线、训练评价、真实模型适配与验证。models/ecg_founder/manifest.json 是尚未启用的12导联扩展参考，不适配当前单导联输入。eval/model_eval_report.py 只根据真实预测列表计算指标，不再返回固定精度。

依据[根 README](../README.md)，现有 pipeline 已包含 evidence 与 explanation_detail。解释默认使用模板；可选外部解释调用和 OpenECG 分类器均需单独验证。配置与限制见[模型策略](docs/model_switch.md)，评价用法见[评估说明](eval/README.md)。

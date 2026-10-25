# 唐一可：AI 算法与分析集成

`pipeline.py` 是统一入口，串联信号质量筛查、测量指导、分类器、可追溯概念证据和解释生成。

当前输出包含三态决策：

- `signal_invalid`：信号不合格，跳过分类并要求复测。
- `model_uncertain`：模型未加载、置信度不足或信号存在干扰，不展示确定性分类。
- `assistive_classification`：达到辅助展示要求，可提供非诊断性的节律分类。

`quality/coach.py` 提供工程质量指标，包括基线漂移、疑似工频干扰、运动突变、信噪比代理值和信号评分，并生成具体复测动作。调用方可以在输入中附加 `previous_quality`，让 `measurement_coach.verification.comparison` 返回本次与上次的评分变化。

质量教练是测量和结果展示的安全层，不是临床诊断器。当前模型默认不加载；设置 `ECG_MODEL_TYPE=openecg` 后才启用 OpenECG，未加载模型时返回 `model_unavailable`，但决策状态为 `model_uncertain`。

`models/ecg_founder/manifest.json` 是尚未启用的 12 导联扩展参考，不适配当前单导联输入。`eval/model_eval_report.py` 只根据真实预测列表计算指标，不返回固定精度。

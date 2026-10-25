# OpenECG 患者级评估

当前评估任务是**记录级节律筛查**，不是逐心拍分类或临床验证。仓库不携带 PTB-XL 全量信号；先从 [PhysioNet PTB-XL v1.0.3](https://physionet.org/content/ptb-xl/1.0.3/) 按其许可和引用要求下载 500 Hz 数据，再运行以下脚本。

## 划分与标签

- 使用官方 `strat_fold`，fold 1–8 为开发数据，fold 9–10 固定作为测试数据。
- 脚本会验证每个 `patient_id` 不跨 fold，并导出完整患者/记录清单。
- 标签映射版本为 `ptbxl-scp-record-level-v1`：明确 `AFIB` 映射房颤；只有无其他诊断码时 `NORM` 才映射 normal；其他已识别诊断统一归入 other_abnormality；无支持诊断标签的记录不纳入评估。
- 这是针对当前 OpenECG 标签集合的保守工程映射，不等同数据集官方分类语义，需由团队/领域人员复核后再冻结。

## 先生成并审核患者级清单

在仓库根目录执行：

```powershell
python -m pip install wfdb
python -m ai_model.eval.ptbxl_patient_eval --metadata <PTBXL目录>\ptbxl_database.csv --output-dir runtime\ptbxl_eval --manifest-only
```

先审核 `runtime/ptbxl_eval/ptbxl_patient_fold_manifest.csv` 的标签和患者折叠；确认映射方案后再运行推理。该 CSV 应保留在 runtime，不提交任何心电信号或个人级数据。

## 运行冻结测试折

确保项目配置了 `ECG_MODEL_TYPE=openecg` 且 OpenECG 可用：

```powershell
python -m ai_model.eval.ptbxl_patient_eval --metadata <PTBXL目录>\ptbxl_database.csv --records-root <PTBXL目录> --output-dir runtime\ptbxl_eval --folds 9,10 --lead II
```

输出：

- `ptbxl_metrics.json`：混淆矩阵、Accuracy、Macro-F1、各类召回率/敏感度/特异度、覆盖率和拒答数。
- `ptbxl_predictions.json`：每条测试记录的患者 ID、真值、原始预测、置信度、质量、决策和失败原因。
- `ptbxl_errors.csv`：错分、拒答或运行失败记录，供人工错误分析。
- `ptbxl_patient_fold_manifest.csv`：完整元数据到标签映射的审计清单。

当前固定质量门槛 70 和置信度门槛 0.55 是工程策略，不是医学阈值。脚本不会把拒答样本当正确，指标同时报告拒答惩罚后的结果和覆盖率。评估真实运行前必须审核标签映射、下载数据并确认模型输入要求；没有完成推理时不得引用指标作为模型表现。

# OpenECG 患者级评估

当前评估任务是**记录级节律筛查**，不是逐心拍分类或临床验证。仓库不携带 PTB-XL 全量信号；先从 [PhysioNet PTB-XL v1.0.3](https://physionet.org/content/ptb-xl/1.0.3/) 按其许可和引用要求下载 500 Hz 数据，再运行以下脚本。

## 划分与标签

- 使用官方 `strat_fold`：fold 1–8 仅作训练/参考，fold 9 用于阈值开发，fold 10 冻结为最终测试集。
- 脚本会验证每个 `patient_id` 不跨 fold，并导出完整患者/记录清单。
- 标签映射版本为 `ptbxl-rhythm-only-v3`：`AFIB` 映射房颤；明确的 PVC、PAC、心动过速/过缓等支持节律码映射为 other_abnormality。正权重 `NORM` 单独出现或仅搭配 `SR` 时映射 normal；`SR: 0` 不按缺失处理。含 `ABQRS` 或其他额外代码的正常候选仍排除。心肌梗死、传导或形态学诊断不再自动算作节律异常，而是排除为任务不匹配。
- 这是针对当前 OpenECG 标签集合的保守工程映射，不等同数据集官方分类语义，需由团队/领域人员复核后再冻结。

## 先生成并审核患者级清单

在仓库根目录执行：

```powershell
python -m pip install wfdb
python -m ai_model.eval.ptbxl_patient_eval --metadata <PTBXL目录>\ptbxl_database.csv --output-dir runtime\ptbxl_eval --manifest-only
```

先审核 `runtime/ptbxl_eval/ptbxl_patient_fold_manifest.csv` 的标签和患者折叠；确认映射方案后再运行推理。该 CSV 应保留在 runtime，不提交任何心电信号或个人级数据。

## 阈值开发与冻结测试

### 第9折调试样本（每类100条）

先用固定随机种子生成患者去重的抽样清单并下载对应 WFDB 文件。每类最多选择100位不同患者、每位患者只选一条记录，类别之间也不会重复患者。抽样清单及信号文件保存在 `runtime/`，不提交到 Git。确认映射已审核后，在仓库根目录的 PowerShell 执行（metadata 路径按本机情况修改）：

```powershell
.\.venv\Scripts\python.exe -m ai_model.eval.ptbxl_patient_eval `
  --metadata "D:\ptbxl_database.csv" `
  --output-dir ".\runtime\ptbxl_fold9_sample" `
  --sample-fold 9 `
  --per-class 100 `
  --seed 20261025 `
  --records-root ".\runtime\ptbxl_eval" `
  --download
```

清单位于 `runtime/ptbxl_fold9_sample/ptbxl_fold9_sample_manifest.csv`，信号文件位于 `runtime/ptbxl_eval/records500/...`。下载被网络中断时可重跑相同命令，已存在的非空文件会跳过。

### 评测及最终测试

确保项目配置了 `ECG_MODEL_TYPE=openecg` 且 OpenECG 可用。映射版本 `ptbxl-rhythm-only-v3`、模型、预处理、阈值及开发清单应先审核并冻结；第9折仅用于调试/阈值开发，不根据第10折结果调参。冻结后再运行第10折最终测试：

```powershell
.\.venv\Scripts\python.exe -m ai_model.eval.ptbxl_patient_eval `
  --metadata "D:\ptbxl_database.csv" `
  --records-root ".\runtime\ptbxl_eval" `
  --output-dir ".\runtime\ptbxl_dev" `
  --folds 9 `
  --lead II

.\.venv\Scripts\python.exe -m ai_model.eval.ptbxl_patient_eval `
  --metadata "D:\ptbxl_database.csv" `
  --records-root ".\runtime\ptbxl_eval" `
  --output-dir ".\runtime\ptbxl_test" `
  --folds 10 `
  --lead II
```

输出：

- `ptbxl_metrics.json`：混淆矩阵、Accuracy、Macro-F1、各类召回率/敏感度/特异度、覆盖率和拒答数。
- `ptbxl_predictions.json`：每条测试记录的患者 ID、真值、原始预测、置信度、质量、决策和失败原因。
- `ptbxl_errors.csv`：错分、拒答或运行失败记录，供人工错误分析。
- `ptbxl_false_negatives.csv`：真实异常但输出 normal 的最高优先级复核清单。
- `ptbxl_error_analysis.json`：异常漏检率及质量门槛、置信度、运行错误等原因分类汇总。
- `ptbxl_patient_fold_manifest.csv`：完整元数据到标签映射的审计清单。

当前固定质量门槛 70 和置信度门槛 0.55 是工程策略，不是医学阈值。脚本不会把拒答样本当正确，指标同时报告拒答惩罚后的结果和覆盖率。评估真实运行前必须审核标签映射、下载数据并确认模型输入要求；没有完成推理时不得引用指标作为模型表现。

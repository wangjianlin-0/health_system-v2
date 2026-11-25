# AI 模型评估

2026-11-16 v3真实波形重评已完成，见[OpenECG v3节律优化及实测](../../docs/OPENECG_V3_EVALUATION.md)。本地fold9纳入32条、排除7条，样本不均衡；不可与历史29条直接比较。

2026-11-16：完整的历史证据、当前验证边界及复现命令见[模型测评报告与复现方法](../../docs/MODEL_EVALUATION_REPORT.md)。历史PTB-XL指标可使用 `python -m ai_model.eval.audit_saved_report --report-dir runtime/ptbxl_report` 离线复算；当前波形重评使用恢复并适配后的 `ptbxl_patient_eval.py`，标签映射和质量算法与旧报告不同。

模型模块负责标签、患者级划分和真实预测评价；信号模块负责来源、许可与解析。以[根 README](../../README.md)为准，当前无已验收模型性能。

## 数据集

合成 clean/noise 数据只用于开发联调，不能当临床独立测试集。真实测试数据需许可、患者隔离和标签版本，仓库不预置真实数据集。

## 脚本

- generate_test_data.py 生成合成 JSON，旧字段 signal/sample_rate 需适配为标准输入，不可直接上传为 CSV。
- model_eval_report.py 读取真实预测列表，计算 macro_f1、每类 precision/recall/f1/support 与混淆矩阵；不运行模型，不输出固定精度。

## 用法

从仓库根目录执行；合成脚本额外需要 numpy：

```powershell
python ai_model/eval/generate_test_data.py --type clean --output data/eval_clean --count 10
python ai_model/eval/model_eval_report.py predictions.json
```

predictions.json 为非空 JSON 列表，每项含 true_label 和 predicted_label，须由真实独立测试预测产生。手写样例只能验证计算。报告同时记录患者划分、数据/处理/模型版本与限制。

PTB-XL评测默认使用 `--quality-gate hard`，只拒绝长度不足、空信号、平直、疑似导联脱落、状态帧异常或R峰检测明显不可靠等硬性无效记录；0–100质量评分仍写入结果，但不会单独造成拒识。若要复现旧版“低于阈值即拒识”的工程逻辑，显式使用：

```powershell
.\.venv-run\Scripts\python.exe -m ai_model.eval.ptbxl_patient_eval `
  --metadata D:/ptbxl_database.csv `
  --records-root runtime/ptbxl_eval `
  --folds 10 `
  --quality-gate score `
  --quality-threshold 70 `
  --output-dir runtime/ptbxl_fold10_score_gate
```

新评测建议保留默认硬门控：

```powershell
.\.venv-run\Scripts\python.exe -m ai_model.eval.ptbxl_patient_eval `
  --metadata D:/ptbxl_database.csv `
  --records-root runtime/ptbxl_eval `
  --folds 10 `
  --quality-gate hard `
  --output-dir runtime/ptbxl_fold10_hard_gate
```

## 负责人更新

2026-10-21：修正 CLI，区分合成数据与真实评价。

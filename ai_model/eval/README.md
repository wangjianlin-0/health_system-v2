# AI 模型评估

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

## 负责人更新

2026-10-21：修正 CLI，区分合成数据与真实评价。

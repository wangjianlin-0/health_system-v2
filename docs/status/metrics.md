# 模型指标

## 版本与依据

2026-10-21，依据[根 README](../../README.md)。模型模块负责模型评价。软件[验证记录](../VALIDATION.md)不是模型性能报告。

## 当前状态

| 模型 | 状态 |
|---|---|
| 首版单导联基线 | 待训练和独立患者级评价 |
| 可选 OpenECG | 适配代码存在，真实加载与性能未验收 |
| ECGFounder | 12 导联扩展，manifest 为 pending |
| ECG-Arrhythmia | 原候选，未接入 |

## 目标指标

原 Accuracy ≥95%、Sensitivity ≥90%、Specificity ≥95%、Latency <500ms 既非实测，也非本轮确认的验收门槛；任务与测试集明确后再确认。

| 指标 | 报告要求 |
|---|---|
| macro-F1、每类 precision/recall/F1/support、混淆矩阵 | 当前脚本从真实预测计算 |
| Accuracy、Sensitivity、Specificity | 如采用，补计算并明确类别和平均方式 |
| Latency | 固定环境、输入时长并实测统计 |

## 风险评估

患者泄漏、合成数据冒充真实性能、基础检查冒充正式质量均需单独验证。记录数据、处理和模型版本。

## 更新记录

2026-10-21：去除固定指标承诺，区分默认不可用与可选适配。

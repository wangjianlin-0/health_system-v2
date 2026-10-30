# 模型权重清单

## 待补充

依据[根 README](../../README.md)，模型模块优先交付单导联模型。

- [ ] 来源、许可、标签与患者级划分、权重位置及校验值。
- [ ] 处理配置、运行依赖和独立测试评价。
- [ ] 可选 OpenECG 的依赖、实际权重和推理验证。
- [ ] ECGFounder 12 导联权重为扩展项。

## Manifest 校验

ai_model/models/ecg_founder/manifest.json 为 pending，声明 12 导联、500 Hz、10 秒；输出数值仅为示例，不是实测结果，也不能覆盖真实采样率。仓库不存在 scripts/validate_model.py，不能沿用原命令。

```powershell
Get-Content ai_model/models/ecg_founder/manifest.json
```

以上只查看清单，不验证权重或推理能力。实际校验工具待模型作者交付。

## 负责人更新

2026-10-21：纠正不存在的校验命令与模型状态。

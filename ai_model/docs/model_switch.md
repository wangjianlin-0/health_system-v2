# 模型切换与回退策略

## 模型列表

| 模型 | 用途 | 优先级 |
|------|------|--------|
| ECGFounder | 官方权重就绪后的单导联/多导联适配 | 待权重和输入规范确认 |
| ECG-Arrhythmia | 实时心律检测 | 备 |

## 切换流程

```
Request → ECGFounder adapter → 成功 → Response
                 ↓ 权重/输入不满足
         model_unavailable（不伪造分类）

当前项目默认仍使用 OpenECG；切换前必须确认 ECGFounder 官方单导联权重。

```powershell
$env:ECG_MODEL_TYPE = 'ecgfounder'
$env:ECGFOUNDER_WEIGHTS = 'C:\path\to\ecgfounder\weights'
```

当前仓库的 `manifest.json` 仍是 `status: pending` 且要求 12 导联，因此切换后会明确返回“模型不可用”，不会把单导联复制成 12 导联。
```

## 熔断机制

- 失败阈值: 连续 5 次
- 恢复超时: 30 秒
- 告警: 熔断时通知

## 负责人更新

| 日期 | 更新内容 |
|------|----------|

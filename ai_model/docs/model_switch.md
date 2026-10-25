# 模型切换与回退策略

## 模型列表

| 模型 | 用途 | 优先级 |
|------|------|--------|
| ECGFounder | 12 导联完整分析 | 主 |
| ECG-Arrhythmia | 实时心律检测 | 备 |

## 切换流程

```
Request → ECGFounder → 成功 → Response
              ↓ 失败
       ECG-Arrhythmia → Response (标记 fallback)
```

## 熔断机制

- 失败阈值: 连续 5 次
- 恢复超时: 30 秒
- 告警: 熔断时通知

## 负责人更新

| 日期 | 更新内容 |
|------|----------|

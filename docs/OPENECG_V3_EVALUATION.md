# OpenECG v3节律任务优化及实测

日期：2026-11-16。未修改模型权重、置信度阈值0.55或质量阈值70；本次优化的是任务定义、评测追溯和错误分析，不宣称模型精度提高。

## 实施内容

恢复的v3映射已排除仅有MI、ST-T等形态诊断的记录。本次修正过时说明，明确 `other_abnormality` 在本评测中仅指显式支持的非AF节律标签，不代表所有心脏异常。AFIB与MI等诊断可以共存，不应仅因MI排除AFIB；对应回归断言已补充。

新增 `ai_model/eval/local_rhythm_eval.py`，冻结本地波形可用集合并保存排除原因，避免将缺文件当成模型错分。批量报告新增全元数据映射状态数量、具体节律码样本数/正确数/拒答数；完整原始标签仍保留供复核。质量算法版本逐条保存。

## 数据与限制

使用 D:\ptbxl_database.csv 和 runtime/ptbxl_eval 中已有的500 Hz WFDB文件，II导联、前10秒、mV。只运行开发fold9，未使用fold10调整阈值。

fold9可用39条，排除任务不匹配7条；纳入32条、32名患者：正常3条、AF28条、其他节律1条。是本地便利样本，包含此前已查看的病例，不是新的独立测试集；不能代表完整fold9或真实人群。

## 实际结果

- 正确22/32，Accuracy（含拒答算错）68.75%。
- Macro-F1（固定三类，拒答计漏检）59.6776%。
- 覆盖率96.875%，拒答1条，为质量门控；无执行错误。
- normal：Precision100%，Recall66.6667%，F1 80%，支持数3。
- AF：Precision100%，Recall67.8571%，F1 80.8511%，支持数28。
- other：Precision10%，Recall100%，F1 18.1818%，支持数1。

行真实normal/AF/other，列预测normal/AF/other/拒答：

```text
normal   2   0  1  0
AF       0  19  8  1
other    0   0  1  0
```

AF的8条错分均输出原始类别bbb；另外1条AF因质量被拒答。全体预测原始类别为afib19、bbb9、paced1、sinus2，另外1条未进入推理。不能因“异常未判正常为0”忽略AF被错分或拒答。

历史29条v1的68.97%/67.13%与当前结果不构成性能升降对照：样本、标签映射和质量算法均不同。当前other仅1条，Recall100%没有总体估计意义。

## 尚存任务不匹配

v3仍是粗粒度工程评测：PTB-XL中STACH/SBRAD等可描述窦性心率，而适配器的sinus统一映射normal；房扑也不等于房颤。评测保留具体节律码，后续应按“节律类型、心率状态、传导、异位心拍”分任务，并复核BBB与AF是否共存。不能为了提高分数，将模型输出事后改成真实标签或把所有异常合为一类后宣称AF识别变好。

## 复现

```powershell
cd C:\Users\tangyike\Desktop\EGC\health_system-v2
$env:ECG_EXPLANATION_PROVIDER = 'template'
.\.venv-run\Scripts\python.exe -m ai_model.eval.local_rhythm_eval `
  --metadata D:/ptbxl_database.csv `
  --records-root runtime/ptbxl_eval --fold 9 `
  --output-dir runtime/ptbxl_v3_local_fold9_rerun
.\.venv-run\Scripts\python.exe -m pytest tests/test_ptbxl_patient_eval.py -q
```

需安装wfdb及openecg；本次已在.venv-run安装wfdb4.3.1并通过pip check。本地文件集合变化会影响选择结果，因此复现本次精确集合时应使用 `runtime/ptbxl_v3_local_fold9/selection_audit.json` 的record_ids，传给原批量入口 `--record-ids`，而不是重新扫描扩大的目录。

原始输出保存在 runtime/ptbxl_v3_local_fold9：selection_audit.json、ptbxl_metrics.json、ptbxl_predictions.json、ptbxl_errors.csv、ptbxl_error_analysis.json、ptbxl_false_negatives.csv和患者清单。旧runtime/ptbxl_report未修改。

下一步应先人工复核8条AF→BBB的波形与共病，再建立数量充足、预先冻结、按具体节律分层的开发集；完成规则或模型优化后在未查看的独立患者上验证。现阶段没有证据宣称提高了模型本身准确率。

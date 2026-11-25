# 模型测评报告与复现方法

整理日期：2026-11-16。代码基线：`0e58a2678c62c53f15ad4b4cc2c79063389a2c5e`，另含本地恢复及适配后的 PTB-XL 评测脚本。

本报告汇总已有证据，并区分历史研究评价、当前软件一致性检查与真实设备外部评价。本次未重新训练模型，也未重新运行完整波形精度评测。下列历史指标不是当前设备或临床性能承诺。

## 1. 总体结论

- CNN H27：有26名开发患者的患者隔离三折 OOF 评价协议；当前可核对权重和黄金向量。没有在本报告中取得完整可核验的总体数值报告，因此不填写准确率。
- HGB v92：有历史自动检测、切拍、分类端到端开发评价，hp05 模式 Macro-F1 为86.1196%。S类精确率较低，部分患者漏检明显。不是封存患者独立测试。
- OpenECG：历史 PTB-XL 29条、29名患者评测，Accuracy 68.9655%、Macro-F1 67.1345%；原预测明细和指标报告均保留，可离线复算。
- R峰回退、呼吸、质量评分：有功能或合成场景验证，没有当前设备独立标注集的完整准确度报告。
- 安全规则：确定性逻辑，需验证规则覆盖和边界；不是分类模型。
- 大模型解释：有结构约束及回退测试，未建立专家审核的医疗解释正确率报告。

功能测试通过不等于分类准确率合格。模型输出概率也不等于实际正确率。不同数据集、标签层级的 Macro-F1 不可直接比较排名。

## 2. 模型职责与输入约定

CNN/HGB负责逐拍定位和分类，当前适配器要求500 Hz单导联原始mV；不得用修改采样率字段代替真实重采样。原冻结预处理及特征必须保持一致。

CNN输出 N/S/V/F，F是融合心拍。HGB输出 N/S/VF，其中VF是V/E/F合并，绝不是心室颤动。OpenECG负责记录级节律；当前适配器使用输入前10秒，因此长记录结果不能表述为整段均已分析。

历史上给出的“R峰前250 ms、后450 ms”只是通用数据集举例，不是当前冻结CNN的训练规格。CNN实际使用归一化wave128及RR、历史背景等输入；HGB配置固定window_before=178、window_after=267和192维特征。新训练必须读取各模型协议，不能用通用350点窗口替换。

## 3. HGB v92历史评价

证据：`ai_model/vendor/ecg_edge/model/inference/evidence/evaluation_summary.json` 的 `versions.v92.modes.hp05.pooled`；说明见同目录下 `docs/records/integration_audit.md`。

主开发数据为INCART，训练还使用协议允许的MIT辅助数据；精确记录、导联和辅助库范围应以原始训练协议为准，不能只凭简称推断为某一个MIT数据库。26名INCART开发患者三折隔离；另封存8、10、22、23、31、32六名患者，现有交接检查没有加载封存患者。

真实类别支持数：N=125997，S=1508，VF=16411，共143916个标注心拍。

- N：Precision 99.3474%，Recall 98.4722%，F1 98.9079%。
- S：Precision 53.7086%，Recall 81.6313%，F1 64.7895%。
- VF：Precision 92.6538%，Recall 96.7583%，F1 94.6615%。
- Macro-F1：86.1196%。

混淆矩阵：行是真实N/S/VF，列是预测N/S/VF/未匹配或缺失。

```text
N    124072   799    522   604
S        65  1231    205     7
VF      344   108  15879    80
```

另有未匹配额外预测N=406、S=154、VF=532；原报告精确率包含这些假阳性，不能只用上面的矩阵列和计算精确率。

F子类命中107/161；患者30的S仅命中4/161；每分钟计数MAE为0.890164拍/分钟，最差分钟少计54拍。原逐类、逐患者及计数目标未全部达到。raw模式Macro-F1为83.2555%，不能与hp05模式混用。

## 4. CNN H27历史证据

来源：`ai_model/vendor/ecg_edge/model/cnn_fourclass/protocol.json`。

采用与HGB对应的26名INCART开发患者三折OOF协议，六名封存患者排除；辅助训练策略包含SVDB记录级采样，而SVDB记录不等于已核验患者。历史训练使用TRAIN-only HGB软目标，推理不需要HGB教师。

协议明确标注：N/S/V精确率、召回率及F1向95%优化的目标未达到；INT8未验证，hardware=false。当前可执行三折黄金向量和本地CPU推理核对，但不能从黄金向量推导总体分类精度。

包内CNN完整重放入口还引用原来源工程的准备模块及历史证据文件。没有补齐原始数据、协议、依赖和冻结缓存前，本仓库不宣称能够直接完整重现原训练轨迹或全部OOF分数。

## 5. OpenECG历史外部评价

报告日期2026-10-25，数据为PhysioNet PTB-XL v1.0.3的500 Hz记录，II导联、mV，读取前10秒，无额外滤波。历史标签映射版本 `ptbxl-scp-record-level-v1`，模型标识 `openecg-codec-v6`，置信度阈值0.55，质量阈值70。

原报告从官方fold 9/10选取29条、29名患者，并记录与fold 1–8元数据患者隔离检查通过。这不是完整PTB-XL测试集，也不能排除第三方预训练数据与公开评测库的潜在重叠。

- 正确20/29；Accuracy（拒答算错）68.9655%。
- Macro-F1（拒答计入漏检）67.1345%。
- 覆盖率100%，拒答0。
- normal：10条，Precision 57.1429%，Recall 80%，Specificity 68.4211%，F1 66.6667%。
- atrial_fibrillation：9条，Precision 90%，Recall 100%，Specificity 95%，F1 94.7368%。
- other_abnormality：10条，Precision 60%，Recall 30%，Specificity 89.4737%，F1 40%。

混淆矩阵：行是真实normal/AF/other，列是预测normal/AF/other/abstain。

```text
normal    8  0  2  0
AF        0  9  0  0
other     6  1  3  0
```

9条错分中6条为其他异常被预测正常；19条异常中6条被预测正常，占31.58%。另外1条other预测AF，2条normal预测other。other漏检包含标签任务不匹配的影响，不能全部解释为节律模型漏诊。9例AF全部命中也不能据此断言真实人群敏感度100%。

历史报告位置：`runtime/ptbxl_report/`，包含 `ptbxl_metrics.json`、`ptbxl_predictions.json`、`ptbxl_errors.csv` 和 `ptbxl_patient_fold_manifest.csv`。runtime是本地资产，不保证随Git分发，分享时须单独保留去标识报告。

## 6. 其他模块的测评边界

呼吸：合成60秒案例曾输出约14.9次/分及13个周期，只能证明算法运行；需同步呼吸带/鼻气流，统计呼吸率MAE、偏差、一致性及暂停事件召回。

质量：确定性质量指标及双检测器bSQI有场景测试；无人工标注质量集上的敏感度/特异度。0–100分不是医学标准，也不是概率。

R峰回退：需在逐拍标注下报告检测容差、Se、PPV、F1及心率MAE，目前不填写未测数值。

解释大模型：需专家盲审事实一致性、遗漏、无依据因果解释和不安全建议；JSON校验通过不等于内容医学正确。安全规则则需边界及缺失输入测试。

## 7. 复现环境

所有命令在Windows PowerShell、项目根目录执行：

```powershell
cd C:\Users\tangyike\Desktop\EGC\health_system-v2
$env:ECG_EXPLANATION_PROVIDER = 'template'
.\.venv-run\Scripts\python.exe -m pip check
.\.venv-run\Scripts\python.exe -c "import sys, importlib.metadata as m; print(sys.version); print({p:m.version(p) for p in ['numpy','scipy','torch','pytest']})"
```

整理时实际环境：NumPy 2.5.4、SciPy 1.18.1、CPU Torch 2.15.0+cpu、pytest 9.2.0；OpenECG可找到，但WFDB缺失。这是当前环境快照，不是2026-10-25原实验完整锁定环境。实际波形重评前安装并检查：

```powershell
.\.venv-run\Scripts\python.exe -m pip install wfdb
.\.venv-run\Scripts\python.exe -c "import wfdb, openecg; print('依赖正常')"
.\.venv-run\Scripts\python.exe -m pip freeze | Out-File runtime\evaluation_environment.txt -Encoding utf8
```

不要将.env、密钥或虚拟环境上传到报告附件。

## 8. 复现A：离线复算历史29条指标

此步骤只读取已保存真实标签和预测，不调用OpenECG、不下载波形、不需要WFDB。

```powershell
.\.venv-run\Scripts\python.exe -m ai_model.eval.audit_saved_report --report-dir runtime/ptbxl_report
```

预期 `verified=true`，29条、29名患者，指标与历史报告逐字段匹配。只能验证统计一致性，不能验证真实波形来源、标签正确性或原推理过程。

## 9. 复现B：当前版本波形重评

元数据：`D:\ptbxl_database.csv`；波形根：`runtime/ptbxl_eval`，不要再附加records500。先验证恢复脚本：

```powershell
.\.venv-run\Scripts\python.exe -m pytest tests/test_ptbxl_patient_eval.py -q
.\.venv-run\Scripts\python.exe -m ai_model.eval.ptbxl_patient_eval --help
```

当前标签映射为 `ptbxl-rhythm-only-v3`，质量接口为 `QualityCoach.assess()`。v3排除单纯形态诊断，fold9用于阈值开发、fold10用于最终评价；与历史v1及旧质量算法不同，重评不保证仍为29条或相同分数。

下载fold9每类100名患者的冻结抽样（每类不足时脚本报错，不伪造样本）：

```powershell
.\.venv-run\Scripts\python.exe -m ai_model.eval.ptbxl_patient_eval `
  --metadata 'D:\ptbxl_database.csv' --records-root runtime/ptbxl_eval `
  --sample-fold 9 --per-class 100 --seed 20261025 --download `
  --output-dir runtime/ptbxl_fold9_current_sample

$recordIds = (Import-Csv runtime/ptbxl_fold9_current_sample/ptbxl_fold9_sample_manifest.csv |
  ForEach-Object { $_.record_id }) -join ','
.\.venv-run\Scripts\python.exe -m ai_model.eval.ptbxl_patient_eval `
  --metadata 'D:\ptbxl_database.csv' --records-root runtime/ptbxl_eval `
  --folds 9 --record-ids "$recordIds" --confidence-threshold 0.55 `
  --quality-threshold 70 --output-dir runtime/ptbxl_fold9_current_report
```

阈值确定后，把抽样命令中的9改为10并采用新的fold10目录，再读取对应清单运行 `--folds 10`。禁止根据fold10反复优化。此前29条已查看记录涉及的患者应通过 `--exclude-reviewed-ids` 排除，并保存排除名单；排除会改变样本数，应如实记录。

检查每条预测的 `failure_reason`、`decision_state` 和覆盖率。缺波形、缺库、输入错误属于执行失败，不能直接当作模型低准确率。保留指标、完整预测、错误/漏检记录和患者清单，输出使用新目录，不能覆盖历史29条报告。

## 10. 复现C：CNN/HGB软件一致性

```powershell
.\.venv-run\Scripts\python.exe scripts/check_pc_models.py
```

入口验证资产SHA、CNN三折黄金向量、HGB合成链路及真实适配器推理，输出 `runtime/verification/pc_models.json`。通过只表示实现与冻结参考一致。缺少原INCART开发波形和冻结处理协议时，不能仅靠此命令重新计算86.1196%的开发集分数。

HGB历史摘要可直接查看：

```powershell
$summary = Get-Content ai_model/vendor/ecg_edge/model/inference/evidence/evaluation_summary.json -Raw | ConvertFrom-Json
$summary.versions.v92.modes.hp05.pooled | ConvertTo-Json -Depth 8
```

## 11. 正式验收与交付要求

冻结数据版本、原始文件SHA、患者名单、标签映射、导联、采样率、单位、预处理、权重SHA、依赖版本、阈值、拒答规则及命令行。心拍任务还需报告检测匹配时间容差、漏检及额外检测计分方式，不能仅评价成功切片。

真实ADS1292R/Zynq外部测试需独立受试者、人工复核标注；呼吸需参考设备。报告逐类支持数、Precision/Recall/F1、混淆矩阵、患者级分布、置信区间及失败率。置信区间应按患者聚类估计，不能把同一患者大量心拍视为独立个体。

结论：现有系统具备历史研究评价及可运行的评测框架；OpenECG小样本指标可从保存预测复算，CNN/HGB可做冻结实现一致性检查。但尚无覆盖全部模块、当前设备和独立人群的全面临床准确度结论。

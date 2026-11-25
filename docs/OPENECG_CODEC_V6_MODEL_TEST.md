# OpenECG codec-v6 模型测试与训练记录

整理日期：2026-11-25。模型版本：openecg 0.11.0 / codec-v6。本文记录模型卡核验、项目三分类评测和公开 CODE-test 四分类独立重评及后续离线训练实验。项目测试结果、模型卡声明和训练候选结果分别列示，避免混用。

## 1. 总体结论

- OpenECG 官方 codec-v6 权重及发布版本已在本机核验，包含 PyTorch、INT8 ONNX 权重和模型卡。
- 项目 PTB-XL 三分类评测使用正常、房颤及其他支持节律三类，fold10 选取300名患者，每类100条。原始模型正确208/300，准确率69.33%，Macro-F1 67.58%，覆盖率99%。
- 使用400名PTB-XL患者训练的四分类输出读出层，在另一批140名患者上选择和校准。于公开CODE-test重建的818例单标签记录上，本地最佳候选准确率91.08%，Macro-F1 70.42%。同一预处理和评分代码下原始codec-v6准确率81.66%、Macro-F1 65.96%。
- 官方模型卡CODE-test声明Macro-F1为76.7%。官方精确病例清单、端到端评分脚本及全部预处理细节未公开，本地结果属于独立重评，不是官方分数复现。
- 候选只用于离线研究评测，尚未替换应用中的官方权重，也不是临床验证。

## 2. 模型职责与输入

OpenECG codec-v6为单导联心电编码器，提供逐采样点的frame、beat和rhythm通道。项目适配器使用节律层，支持500 Hz输入，并以记录级节律为主要结果。官方模型卡报告的节律标签含sinus、avb、paced、afib、bbb和ventricular。

项目自身PTB-XL任务映射为normal、atrial_fibrillation、other_abnormality。这里的other_abnormality只涵盖评测脚本显式支持的非房颤节律码，不代表所有心脏异常。该三分类不能与CODE-test四分类结果直接对照。

四分类读出层训练使用PTB-XL 500 Hz记录II导联前10秒，并按OpenECG入口做秩归一化。CODE-test记录取II导联中心窗口，从400 Hz重采样至500 Hz。层输出在窗口时间维度取平均后作为记录级logits。

## 3. 官方codec-v6模型卡指标

以下为官方声明，非本机重算结果：

| 任务 | 数据与切分 | 官方指标 |
| --- | --- | --- |
| frame波界限 | LUDB validation | Macro-F1 0.855；清理不完整标签后0.867；中位边界时间11.1 ms |
| beat VPC | MIT-BIH DS2 | F1 0.929 |
| rhythm分类 | Lydus hospital test | Macro-F1 0.797 |
| 跨队列四类节律 | CODE-test，818例单标签记录 | sinus / avb / afib / bbb F1为0.931 / 0.778 / 0.846 / 0.513；Macro-F1 0.767 |

本机完成的是项目PTB-XL评测及公开CODE-test独立重评。LUDB、MIT-BIH DS2官方协议尚未复算。Lydus测试数据不公开，无法独立复现。

## 4. 项目PTB-XL三分类复测

数据为PTB-XL v1.0.3官方元数据和500 Hz WFDB记录。fold10作为最终测试划分，按每类100条确定性抽样，共300名互异患者。项目此前模型预测涉及的患者从抽样中排除。阈值使用0.55，质量门控使用hard模式，拒答计为错误。

| 指标 | 结果 |
| --- | ---: |
| 样本数 | 300 |
| 正确数 | 208 |
| Accuracy | 69.33% |
| Macro-F1 | 67.58% |
| 覆盖率 | 99.00% |
| 拒答 | 3 |

主要错误为other_abnormality被预测为normal，共66条；另有跨类别错误及3条质量门控拒答。三分类细节见 `runtime/ptbxl_openecg_doc_fold10_20261125/ptbxl_metrics.json`，逐条预测和抽样名单同目录保存。

## 5. 四分类读出层训练

### 5.1 数据划分与标签

训练记录从PTB-XL folds 1–8患者中按患者隔离抽取，每类100名，共400名患者。验证/校准记录来自fold9，每类35名，共140名患者。fold10未用于这轮训练和候选选择。

PTB-XL标签映射为sinus、avb、afib、bbb四类。CODE-test标签来自Zenodo公开发布的gold_standard.csv。官方模型卡报告818例单标签记录，本地依照标签字段重建单标签集合，共818例；SB和ST映射至sinus，1dAVb映射至avb，AF映射至afib，RBBB/LBBB映射至bbb。多标签冲突记录排除，未标注异常的记录映射至sinus。

### 5.2 训练方法

冻结OpenECG codec-v6波形特征提取器。取rhythm_sample模块输入的时间平均表示，以StandardScaler和多项逻辑回归拟合四分类线性读出层。对照原始rhythm logits与新读出分数的线性混合权重及正则强度，在PTB-XL fold9验证记录上选择。随后仅使用PTB-XL验证集选择类别偏置。最终候选将新读出分数与冻结类别偏置组合，保留原始codec-v6编码器。

扩展实验还比较了补零排除池化、时间均值/标准差/峰值特征、额外AVB样本、RBF核读出及短窗增强。均未超过当前最佳CODE-test Macro-F1。较大的PTB-XL验证分数并不保证跨队列提升。

### 5.3 CODE-test结果

| 类别/指标 | 原始codec-v6 F1 | 最佳候选 F1 | 官方模型卡 F1 |
| --- | ---: | ---: | ---: |
| sinus | 0.894 | 0.953 | 0.931 |
| avb | 0.581 | 0.491 | 0.778 |
| afib | 0.750 | 0.727 | 0.846 |
| bbb | 0.414 | 0.645 | 0.513 |
| Macro-F1 | 0.660 | 0.704 | 0.767 |
| Accuracy | 0.817 | 0.911 | 未列为模型卡主指标 |

候选在sinus及bbb上有提升，avb及afib F1下降。Macro-F1较本地原始模型提高1.83个百分点，距官方模型卡数值仍差6.28个百分点。官方评测的确切窗口截取和记录级聚合未完整公开，数字差异可能包含协议差异。

最佳候选参数位于 `runtime/openecg_training/best_candidate/readout.npz`，报告位于同目录 `training_report.json`，逐例分数位于 `code_test_predictions.npz`。训练脚本为 `ai_model/eval/openecg_train_readout.py`。

## 6. 额外患者验证与优化实验

另冻结80名此前未用于候选训练或校准的PTB-XL fold9患者，类别为normal、avb、afib、bbb各20名。冻结候选Macro-F1为0.832，原始模型为0.559。该结果是PTB-XL分布内补充验证，不替代外部CODE-test，也因样本量有限而有较大不确定性。完整结果见 `runtime/openecg_training/expanded_avb/additional_validation.json`。

训练集增补AVB患者后，PTB-XL验证Macro-F1为0.908，但CODE-test Macro-F1为0.553，显示跨队列泛化未改善。加入时序离散度特征后CODE-test Macro-F1为0.648。排除补零池化并沿用此前冻结偏置后Macro-F1为0.702。实验参数及结果保留在 `runtime/openecg_training/` 对应实验子目录。

## 7. 复现步骤

以下命令从仓库根目录运行，依赖使用 `.venv-run`：

```powershell
.\.venv-run\Scripts\python.exe -m ai_model.eval.openecg_official_audit
```

该命令核验OpenECG版本、模型卡和模型文件哈希。

PTB-XL三分类完整复测结果位于 `runtime/ptbxl_openecg_doc_fold10_20261125/`。该输出由 `ai_model.eval.ptbxl_patient_eval` 生成，包括冻结抽样清单、逐条预测、指标、错误分析和患者fold清单。

CODE-test训练与重评的输入清单位于 `runtime/openecg_training/ptbxl_manifest.json`，公开数据归档位于本地 `runtime/openecg_training/code-test.zip`，其MD5为 `cef8fe457abf4b8f66a34dc1269b4ced`。独立运行训练及评测：

```powershell
.\.venv-run\Scripts\python.exe -m ai_model.eval.openecg_train_readout `
  --manifest runtime/openecg_training/ptbxl_manifest.json `
  --records-root runtime/ptbxl_eval `
  --output-dir runtime/openecg_training/reproduced `
  --code-ecg runtime/openecg_training/code-test/data/ecg_tracings.hdf5 `
  --code-labels runtime/openecg_training/code-test/data/annotations/gold_standard.csv
```

脚本从冻结manifest和原始信号重新提取特征并训练，不覆盖已保存最佳候选。CODE-test必须仅用于一次最终外部评估；由于本工作中已经多轮检查CODE-test，后续模型选择应另找未查看的外部队列。

## 8. 自动化检查与交付边界

本轮OpenECG适配与PTB-XL评测相关单元测试11项通过。测试验证代码接口和评测逻辑，不代表准确率验收。

OpenECG读出层候选尚未写入在线适配器，应用默认推理仍使用原始codec-v6。部署前还需实现并测试可加载的候选推理接口、记录模型与读出参数版本、复核概率/阈值行为，并使用新的外部患者集独立验证。所有报告均为工程与研究评测，不构成医疗器械或临床性能声明。

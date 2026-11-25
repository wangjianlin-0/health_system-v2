# OpenECG codec-v6官方指标复现审计

日期：2026-11-16。目标是依据OpenECG v0.11.0官方模型卡复现，不把项目PTB-XL评测混入官方指标。

## 结论

目前可以完整复现权重加载、模型版本、文件哈希和单条推理；不能仅靠公开PyPI包完整复算模型卡全部指标。原因不是本项目代码错误，而是官方发布物没有同时提供四套冻结评测数据、精确清单和端到端运行脚本，且Lydus医院数据并非公开下载资产。

因此指标分为：

- 已核验官方声明：模型卡中的公开数值，可追溯但不是本地实测。
- 可部分复现：LUDB、MIT-BIH、CODE-test数据有公开来源，但必须补齐官方固定样本清单、标签映射、窗口策略和评分入口，才能声称严格复现。
- 当前不可独立复现：Lydus hospital test Macro-F1 0.797，因为需要医院数据 `lydus_ecg.npz` 和 `lydus_ecg.duckdb`。

## 官方发布物核验

安装包为openecg 0.11.0，官方仓库 `https://github.com/vitaldb/openecg`，最新对应release为v0.11.0。PyPI安装包已经包含：

```text
codec_v6.pt             4,926,283 bytes
codec_v6_int8.onnx      3,778,653 bytes
codec_v6_MODEL_CARD.md
```

本机 `codec_v6.pt` SHA-256：

```text
4caf710737c4b9024b5b2b79b897af04c13f82f4f8e5f29b7dc4c8309e487a58
```

运行审计：

```powershell
cd C:\Users\tangyike\Desktop\EGC\health_system-v2
.\.venv-run\Scripts\python.exe -m ai_model.eval.openecg_official_audit |
  Out-File runtime\openecg_official_audit.json -Encoding utf8
```

该命令提取官方声明并校验本机资产，不会伪称已经读取评测数据。

## 官方模型卡声明

codec-v6为单导联、500 Hz、10秒、rank-normalized的三头模型。模型卡报告：

- LUDB val波界限Macro-F1 0.855；清理10个不完整标注窗口后0.867；中位边界误差11.1 ms。
- MIT-BIH DS2 VPC F1 0.929。
- Lydus hospital test节律Macro-F1 0.797。
- CODE-test单标签818例：sinus/avb/afib/bbb F1分别为0.931/0.778/0.846/0.513，Macro-F1 0.767；AUROC分别为0.944/0.994/0.999/0.946。

以上在本报告中标记为`published claim`，而非`locally reproduced`。

## 为什么当前不能宣布完全复现

官方仓库v0.11.0包含通用边界指标代码、MIT-BIH加载器、模型权重和模型卡，但没有发布一个从上述冻结数据集直接生成模型卡全部数字的统一脚本。仓库文件树中没有CODE-test或Lydus最终审计入口。模型卡没有给出所有窗口ID、患者清单、类别阈值、聚合细节及CODE-test下载后的完整预处理命令。

Lydus加载器要求环境变量`OPENECG_LYDUS_DIR`下存在约167K窗口的医院数据文件，因此无法从公开模型包自动获取。模型卡0.797不能由PTB-XL替代复算。

CODE-test虽在Zenodo公开引用，但严格复现还需确认数据访问条件、下载版本、818例单标签筛选清单、导联II提取、500 Hz处理、窗口截取、logit聚合及AUROC计算。缺少任一项都只能称独立重评，不能称官方数字复现。

## 可执行的复现阶段

第一阶段先冻结环境和权重：

```powershell
.\.venv-run\Scripts\python.exe -m pip freeze |
  Out-File runtime\openecg_environment.txt -Encoding utf8
.\.venv-run\Scripts\python.exe -m ai_model.eval.openecg_official_audit |
  Out-File runtime\openecg_official_audit.json -Encoding utf8
```

第二阶段使用公开数据逐项重评，但结果必须标注`independent re-evaluation`：

1. LUDB：固定官方val窗口和10条清理名单，调用`openecg.stage2.evaluate`中的Martinez容差评分。
2. MIT-BIH：固定DS2记录划分、AAMI心拍映射、检测匹配容差和额外检测计分，评价VPC F1。
3. CODE-test：获得官方数据后冻结818例清单和标签映射，保存逐例logit/预测，再算F1和AUROC。
4. Lydus：必须由数据持有方提供测试集和评测容器；否则只引用模型卡。

第三阶段应向OpenECG维护者请求或固定以下内容：

- codec-v6评测commit和执行命令；
- LUDB val窗口及10条清理名单；
- MIT-BIH DS2 scorer；
- Lydus患者隔离test清单；
- CODE-test 818例ID、标签映射、阈值及分数聚合代码；
- 官方依赖锁文件及输出JSON。

拿到这些资产后，才可以把`published claim`升级为`independently reproduced`。

## 与本项目结果的关系

本项目v3本地fold9评测为32条不均衡样本，Accuracy 68.75%、Macro-F1 59.68%。它使用PTB-XL节律映射和项目质量门控，不是官方LUDB/MIT-BIH/Lydus/CODE-test协议，因此不能用来验证或否定官方0.797/0.767。

项目报告应写：已核验OpenECG v0.11.0官方权重及模型卡；已独立运行项目数据评测；官方整套数据集指标尚未因缺少冻结评测资产而完成独立复现。

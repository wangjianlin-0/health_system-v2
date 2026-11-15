# 心拍模型完整推理模块

本目录用于队友在电脑端集成现有HGB（直方图梯度提升树）研究模型。包含从500Hz单导联mV数据到自动检测、切拍、192项特征和逐拍N/S/VF结果的完整参考入口；不依赖原仓库的tmp目录、不需要重新训练。

本目录现按集成分支的结构放在`model/inference/`。固定联调配置与原患者分折见[integration_profile.json](integration_profile.json)，具体约定见[联调配置说明](docs/integration_profile.md)。该配置用于显式调用，入口仍要求指定fold和preprocess，不自动投票或选最佳折。

目前是研究集成版本，未选定正式生产模型。三个fold是患者隔离交叉验证模型，必须明确选择，不能默认当作已验收的投票集成。类别VF指原V/E/F合并，**不是心室颤动**；N也不表示受测者没有疾病。

## 开始使用

解压整个目录，使用Python 3.12及requirements.txt中的NumPy、SciPy。Windows x64已附电脑端原生程序；不需要安装Vivado或运行GCC才能推理。依赖缺失时由接收方在自己的虚拟环境配置：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -X utf8 -B check.py
.venv\Scripts\python.exe -X utf8 -B run.py --input examples/synthetic500.csv --fold 0 --preprocess hp05 --output output/beats.csv --features output/features.npz
```

已有依赖时直接使用对应Python运行，不必重复创建环境。输出文件存在时拒绝覆盖，请换新文件名。CSV输入是无标题的单列mV，NPY输入是一维mV数组，均为500Hz、连续无丢样的同一导联。

## 目录

| 位置 | 用途 |
| --- | --- |
| run.py / adapter.py | 命令行入口 / 网页后端可导入的JSON安全函数 |
| ecg_model/ | 原始数据到192项特征与树推理的完整Python代码 |
| native/ / bin/ | 完整C检测/重切源码 / Windows x64主机程序 |
| assets/ | 三份既有v92树权重、Hermite基、FIR参数、192项名称 |
| config.json | 与权重绑定的冻结输入约定；不能自行改窗口/类别来兼容别的模型 |
| examples/ | 纯合成原始心电、旧实现生成的黄金结果、160组合成特征 |
| docs/integration.md | 接口、滤波、时序和接入方法 |
| docs/records/integration_audit.md | 检查报告与实际验证范围 |
| evidence/ | 开发记录回归核对、mV入口核对及原始历史质量摘要 |
| provenance.json / licenses/ | 来源、改动及第三方许可 |

这是电脑侧完整模型模块，不是Vivado/Vitis工程、bitstream或已上板的ARM/FPGA分类实现。接收方可先原样运行，再将整目录放入自己的vendor目录；不要只复制权重文件。

## 源码重建

运行程序已包含Windows x64版本，需要重建时使用本机已有GCC：

```powershell
python -X utf8 -B build_native.py --cc "你的GCC完整路径"
python -X utf8 -B check.py --rebuilt-native
```

默认check.py严格检查原包文件SHA及数值；自行重建会改变二进制时间戳/构建记录，明确使用--rebuilt-native仅跳过bin的原包SHA，仍检查源码、权重、配置与完整数值。Linux/macOS可尝试GCC重建，未在这些系统实测；已验证环境以检查报告为准。

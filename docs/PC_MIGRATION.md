# 电脑模型与蓝牙实时采集

更新：2026-11-12。课程工程根目录为 `team_health_system/`。

## 启动

本机共享 Python 环境：`E:\Environments\Python\pytorch`，Python 3.13、PyTorch 2.9.1+cpu。其他项目可选择该解释器；不用把所有包安装到系统 Python。当前项目原虚拟环境保留，尚未合并清理。

`requirements-pc-lock.txt` 记录了 2026-11-12 验收时的依赖版本。复建当前版本时，请按下方命令安装 CPU PyTorch 和 `requirements-dev.txt`，后者包含计算呼吸率所需的 NeuroKit2。

从工程根目录执行：

```powershell
./start_pc.ps1
```

打开 http://127.0.0.1:8000 ，使用原有账号或注册本地账号。这个入口用同一端口提供已构建网页和 API；无需另开 Vite。若端口占用，可用 `./start_pc.ps1 -Port 8010`。停止服务按 Ctrl+C。数据保存在项目 `runtime/`，不会上传到 GitHub。

首次换电脑时创建自己的共享环境并安装依赖：

```powershell
python -m venv E:/Environments/Python/pytorch
E:/Environments/Python/pytorch/Scripts/python.exe -m pip install torch==2.9.1 --index-url https://download.pytorch.org/whl/cpu
E:/Environments/Python/pytorch/Scripts/python.exe -m pip install -r requirements-dev.txt
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
./start_pc.ps1
```

自定义环境通过 `./start_pc.ps1 -Python '其他路径/Scripts/python.exe'` 指定。共享环境安装了课程后端和测试依赖；OpenECG 未安装到该环境，使用该选项前另装 `requirements-ai.txt`。旧 EXE 不会随源码自动升级；本轮交付是网页源码及启动入口。

## 使用

1. Windows 连接 JDY18 对应的蓝牙 USB 接收器或蓝牙虚拟串口。关闭占用同一串口的商家上位机及比赛网页。
2. 打开“实时监测”，刷新并选择实际串口。默认 115200、8N1、无流控，不发送固件控制命令。
3. 默认协议为比赛工程实物使用的 34 字节（4 组样本）。附带 STM32 源码还有 10 字节（1 组样本）版本；如果设备运行该版本，显式选择 10 字节。不会自行猜测和切换协议。
4. 选择 CNN 或 HGB 后开始采集。CH2 为心电，CH1 原码一并保存。波形每 500 ms 更新，默认显示最近 5 秒的因果 0.5–40 Hz 滤波，也可切换原始 mV。
5. 至少 4 秒后显示模型预览；约每 4 秒对本轮完整前缀重新推理。CPU 忙时跟随实际完成时间更新，始终显示已分析到的时间。在线仅展示至少滞后 2.5 秒的事件；停止后完整复算。此方式没有将独立块的结果拼接成有状态推理。
6. 点击“停止采集”，再“保存并完整分析”。系统将心电和呼吸通道一起提交，分析完成后自动打开历史详情。点“下载原件”可获得 `ecg_raw` 和 `resp_raw` 两列波形。点“导出 CSV”可获得心电波形、整段心率和呼吸率，未算出呼吸率时对应列留空。旧实时记录只要原件仍在且波形匹配，点“重新分析”即可补算。

CSV 导入页同样支持 CNN/HGB/OpenECG/仅检查选择。CNN/HGB 必须是真实 500 Hz 单导联原始 mV；不会通过改填采样率、重复数据或猜单位来兼容。厂商 CSV 必须含 `ecg_raw`，未知单位的 `ecg_filtered` 不作为模型输入。

### 心电纸图片导出

在历史记录详情点击“导出心电图片”。可选择时间范围、25/50 mm/s走纸速度、5/10/20 mm/mV增益，以及原始mV或已保存的离线节律滤波波形。若先查看了波形窗口，导出窗口默认沿用该范围；也可点击“选择完整记录”。每页3行，默认每行10秒，长记录通过上一页/下一页分别下载PNG。

图片使用1 mm小格、5 mm大格的红色网格，带1 mV / 200 ms校准脉冲、时间刻度、记录信息和已存在的模型摘要；仅绘制实际单导联，不生成其他导联或不存在的间期。使用完整波形样本，未复用页面降采样点。每行减去中位值居中并标出基线，不改变增益；大幅伪差增加行高，超过图像上限会提示降低增益或缩短范围。PNG宽2376像素，写入8000像素/米物理分辨率，原尺寸宽297 mm；打印时选原尺寸以保留标尺。

2026-11-12 图片功能验收：前端构建通过；浏览器实际下载、PNG尺寸/CRC/物理分辨率、分页、时间范围、滤波切换及手机宽度检查通过。页面顶部课程原型提示已删除。

## 模型、来源和数值约定

### 融合后的模型职责

- CNN/HGB：逐拍模型，输出 R 峰位置、标准化心拍标签及置信度；顶层 `prediction` 保留所选模型结果，兼容既有 API 和数据库。
- OpenECG：独立节律模型，结果写入 `rhythm_analysis`，不作为 CNN/HGB 的逐拍类别替代。
- NeuroKit2/SciPy：仅在已选择 CNN/HGB 但逐拍模型失败时用于 R 峰回退，不产生 PAC/PVC 类别。
- RespirationAnalyzer：处理独立呼吸阻抗通道，输出呼吸率、周期和规则性；缺少有效周期时明确返回无法判断。
- Safety rules：读取质量、逐拍、节律、心率和呼吸结果，生成确定性的研究提示，不调用模型猜测缺失结论。

默认 `ECG_MODEL_TYPE=none`。网页上传和实时监测会显式传入 CNN/HGB；如需 OpenECG 节律能力，需在运行环境安装 `requirements-ai.txt` 中的依赖。CNN 缺少 PyTorch 时会立即返回 `model_unavailable`，不会等待子进程超时。

来源：[ecg-edge-analysis](https://github.com/lykzr/ecg-edge-analysis)，本地源仓库为 `ecg-edge-analysis-review`，核对时 HEAD 与远端 HEAD 都是 `d83c05616c7d09c3de2aa34d40b1a8042bad0b12`。本次更新提交到课程仓库 `main`，包含此前 `ly-Integration` 中的桌面工作流集成。

| 模型 | 固定联调配置 | 类别 | SHA256 |
|---|---|---|---|
| CNN | H27 FP32 fold0 | N/S/V/F | `16d56a6b1065df35f3e11c4cc285055b421978bd451d5da1b72df8f1744fcfc7` |
| HGB | v92 fold0 | N/S/VF | `375cf45ac1f315ecc517a219cb03340727304db8e7738626ac4b4920a5af00f8` |

权重与完整检测、切拍、特征、原生 Windows x64 程序及源码放在 `ai_model/vendor/ecg_edge/`。保留三折权重、黄金向量、原许可证及来源文件。应用显式使用 fold0 延续比赛联调，不默认投票或按分数选最佳折。没有重新训练，运行不依赖 Zynq、Vivado、FPGA 串口或源工程路径。

模型高通为冻结的一阶因果 0.5 Hz，初始化和 4096 模型码/mV 约定不变。页面显示滤波与模型输入分开。ADC 原始偏移码沿用课程已有换算 `(raw-8388608)*2420/(6*8388608)`；比赛旧文档曾用 `8388607`，本次没有将这种极小标度差异静默混入课程记录。参考电压和增益是标称参数，非仪器标定。

两种模型都是心拍分类，不是整段疾病诊断。N 类不代表健康；HGB 的 VF 是 V/E/F 合并，不是心室颤动。逐拍显示模型概率，整体摘要不使用多数投票或编造“整段置信度”。沿用原始 argmax，本次不引入新的拒判阈值。原模型研究评价不作为本课程硬件上的准确率声明。

## 记录及故障边界

- 采集文件：`runtime/acquisition/<owner>/<session>/capture.bin`、`samples.csv`、`session.json`；历史入库后可通过原件下载取得 CSV。服务关闭会释放端口；刷新、切换页面可重新看到本人的当前会话。
- 每轮最多 200000 点（约 6 分 40 秒）。内存会话最多 32 个，已保存且分析结束的旧会话可从内存移出；磁盘原件保留。保存操作幂等。
- 初始化要求连续三帧确定边界；锁定后帧头或码值不符立即停止；连续 5 秒无数据停止。不自动重连、补点或跨会话拼接。
- 帧不含样本序号或 CRC，源端丢样数量为未知；不能从收包时间或连续的软件时间戳证明无线无丢包。末尾残帧原文保留，未补成样本。
- 实时会话本人可访问，账号授权查看通过入库后的家庭功能进行。后端仅监听本机。

## 验证

```powershell
E:/Environments/Python/pytorch/Scripts/python.exe -X utf8 -B scripts/check_pc_models.py
E:/Environments/Python/pytorch/Scripts/python.exe -m pytest tests -q
cd frontend
npm.cmd run build
```

模型检查包含所有迁入文件 SHA、H27 三折黄金向量、HGB 三折完整合成检测/特征/概率、160 组合成特征，以及 CNN/HGB 适配器实际推理。结果写到 `runtime/verification/pc_models.json`。接口测试还覆盖实际权重上传与换模型重分析、记录保存和原件下载、模拟串口分包与错误、权限及重复保存。

真实 JDY18/ADS1292R 蓝牙端到端、长时间运行与断连恢复仍需设备实测；自动测试不宣称完成硬件验收。Windows 原生检测程序已保留，Linux/macOS 需先按 vendor 中说明从源码重建。

2026-11-12 本地验收：完整后端55项测试通过，无跳过；pip check无依赖冲突；前端生产构建通过。HGB原包完整检查及CNN三折黄金向量通过；60秒合成输入下两个模型均得到73个检测事件、72个可分类心拍。浏览器完成注册登录、实时页加载/刷新、真实CNN上传、HGB换模型重分析及390px响应式检查，无页面脚本错误。真实CNN模拟串口预览、停止后整段复算通过。浏览器截图及结果在 `runtime/verification/`，均使用独立测试数据库，不含实际生理采集数据。最终使用共享环境的start_pc.ps1成功启动，首页HTTP 200；验收时无活动串口，未进行真实蓝牙采集。


## 2026-11-15 发布核验

本次发布包含电脑端 CNN/HGB 推理、ADS1292R 串口采集、逐拍结果、换模型重分析、心电纸 PNG 导出及单端口启动。相对原 main，还包含此前集成分支上的异步分析任务、原件下载、记录备注、波形窗口和趋势图等桌面工作流改进。

2026-11-15 重新验证：后端 55 项测试通过，无跳过；CNN 三折黄金向量、HGB 完整合成链路及两种模型适配器推理通过；前端生产构建通过；浏览器完成模型分析、模型切换、实时页面、心电纸 PNG 实际下载及移动端验证。测试环境另有 Starlette/httpx 弃用提示和 pytest 缓存目录权限提示，不影响通过结果。


个人采集记录、数据库、虚拟环境、验收截图、板内程序备份和商家固件工程均未纳入课程仓库；模型包包含已保留来源与许可的冻结研究权重，运行不需要 FPGA。

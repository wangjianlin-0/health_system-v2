# ADS1292R 双通道接入

## 支持的硬件帧

ADS1292R 连续数据模式每帧为 72 位、9 字节，大端排列：

```text
STAT[23:0] + CH1[23:0] + CH2[23:0]
```

- `STAT[23:20]` 固定为 `1100`，解析器同时检查保留位。
- `CH1`、`CH2` 都按 24 位二补码进行符号扩展，不减 `8388608` 偏移。
- 默认通道映射为 `CH1=呼吸阻抗`、`CH2=单导联 ECG`；自定义板卡必须显式传入映射，不能只依赖芯片型号推断。
- ECG 使用 `mV = signed_count × VREF_mV / (PGA × 2^23)`；默认 `VREF=2420 mV`、`PGA=6`。
- 呼吸值在未提供激励电流、相位和模拟前端标定前只输出相对 ADC 计数，不能标为欧姆。

## AI 分流

```text
STAT ──> 帧合法性、GPIO、RLD、ECG/呼吸导联脱落 ──> 质量门控
CH2  ──> ECG mV ──> 本地质量/NeuroKit2（可选）──> OpenECG/ECGFounder（按配置）
CH1  ──> 呼吸相对波形 ──> 平滑、周期检测、呼吸率和呼吸质量
```

ECG 导联脱落或状态帧异常时，系统将 `classification_eligible=false`，跳过疾病分类并返回复测建议。呼吸导联脱落只会使呼吸结果无效，不会伪造呼吸率。

## Python 直接接收 SPI 字节

```python
from ai_model.pipeline import analyze
from signal_processing.python.ads1292r import decode_spi_frames

signal = decode_spi_frames(spi_bytes, sample_rate_hz=500)
result = analyze(signal)
```

若板卡实际为 `CH1=ECG、CH2=呼吸`：

```python
signal = decode_spi_frames(
    spi_bytes,
    sample_rate_hz=500,
    channel_mapping={'ch1': 'ecg', 'ch2': 'respiration'},
)
```

## CSV 上传

上传接口支持单列 mV，也支持原始帧列：

```csv
status_word,ch1,ch2
0xC00000,1024,-350
0xC00000,1040,-421
```

也兼容设备已滤波的命名列：`ecg_filtered` 与可选的 `resp_filtered`。这两列按有符号 ADC 计数处理。

## 离线导出

```powershell
python -m hardware.export_ads input.csv output_dir
```

输出：

- `ecg_mV.csv`：供 ECG 质量与分类模块使用。
- `respiration_adc.csv`：存在呼吸通道时输出相对波形。
- `metadata.json`：状态摘要、通道映射、标定参数、呼吸工程结果和输入哈希。

这些结果用于工程辅助分析，不构成医疗诊断。

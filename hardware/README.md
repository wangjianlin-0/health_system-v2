# 硬件模块：硬件与采集集成

acquisition.py 通过 ADS1292R 状态字和双通道 ADC 计数生成统一回放样例；真实设备仍未连接。`signal_processing/python/ads1292r.py` 已实现 9 字节 SPI 帧、24 位二补码、LOFF 状态和可配置通道映射。firmware/src/main.c 仍是固件草案；不默认已具备 USB 或无线能力。

后续实现采样/缓存/传输、开始停止、序号丢帧、单位换算与适配器；输出标准信号供统一流水线处理，软件状态展示与两位软件负责人协作。回放可用于联调，不能当真实采集成果。

真实外层协议见[硬件协议](../interfaces/hardware_protocol.md)。上传支持单列 mV、`status_word/ch1/ch2` 和 `ecg_filtered/resp_filtered`；ECG 进入现有 AI，呼吸走独立工程分析。

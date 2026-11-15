# 来源

`ads1292.py` 来自 https://github.com/lykzr/ecg-edge-analysis 的 `src/reference/ads1292.py`，保留原字节。

`windows_serial.py` 保留原 `src/pc/ecg_serial.py` 中 WindowsSerial 及其依赖定义，删除依赖旧 Monitor 的 SerialCapture 包装。用于只读串口、8N1、无流控、不发送复位命令。

原项目提交：d83c05616c7d09c3de2aa34d40b1a8042bad0b12。许可见课程仓库 `ai_model/vendor/ecg_edge/LICENSE`（MIT）。

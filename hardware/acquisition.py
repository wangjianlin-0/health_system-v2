"""硬件模块：ADS1292R 帧回放与未来设备接入。未连接真实设备。"""
import math

from signal_processing.python.ads1292r import signal_from_channels

def sample():
    rate = 250
    ecg_counts = []
    respiration_counts = []
    status_words = []
    for i in range(rate*10):
        t = i/rate
        phase = t % 0.8
        ecg_mv = 0.03*math.sin(2*math.pi*t) + math.exp(-((phase-0.2)/0.015)**2)
        ecg_counts.append(round(ecg_mv * 6 * (2 ** 23) / 2420))
        respiration_counts.append(round(120000 * math.sin(2 * math.pi * 0.25 * t)))
        status_words.append(0xC00000)
    return signal_from_channels(
        respiration_counts,
        ecg_counts,
        rate,
        status_words=status_words,
        source='synthetic_ads1292r_replay',
    )

def device_status():
    return {'connected': False, 'mode': 'replay_only', 'message': '真实设备适配器待硬件模块实现；当前仅支持合成回放'}

"""硬件模块：回放输入与未来设备接入。未连接真实设备。"""
import math

def sample():
    rate = 250
    values = []
    for i in range(rate*10):
        t = i/rate
        phase = t % 0.8
        values.append(round(0.03*math.sin(2*math.pi*t) + math.exp(-((phase-0.2)/0.015)**2), 6))
    return {'samples': values, 'sample_rate_hz': rate, 'unit': 'mV', 'lead': 'synthetic', 'source': 'synthetic_replay'}

def device_status():
    return {'connected': False, 'mode': 'replay_only', 'message': '真实设备适配器待硬件模块实现；当前仅支持合成回放'}

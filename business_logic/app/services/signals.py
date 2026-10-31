"""波形压缩编解码与窗口降采样。"""
from __future__ import annotations

import struct
import zlib

ENCODING = 'f32le+zlib'


def encode(values: list[float]) -> bytes:
    numbers = [float(value) for value in values]
    return zlib.compress(struct.pack(f'<{len(numbers)}f', *numbers)) if numbers else b''


def decode(data: bytes, encoding: str, n_samples: int | None = None) -> list[float]:
    if encoding != ENCODING:
        raise ValueError(f'不支持的波形编码：{encoding}')
    raw = zlib.decompress(data)
    count = n_samples if n_samples is not None else len(raw) // 4
    return list(struct.unpack(f'<{count}f', raw[:count * 4]))


def window_points(segment: list[float], sample_offset: int, rate: float,
                  max_points: int, mode: str = 'envelope') -> list[dict]:
    if not segment:
        return []
    buckets = max(1, max_points)
    size = max(1, -(-len(segment) // buckets))
    points: list[dict] = []
    for start in range(0, len(segment), size):
        chunk = segment[start:start + size]
        if mode == 'mean':
            value = sum(chunk) / len(chunk)
            points.append({'t': round((sample_offset + start + len(chunk) / 2) / rate, 6),
                           'v': round(value, 6)})
            continue
        low = min(range(len(chunk)), key=chunk.__getitem__)
        high = max(range(len(chunk)), key=chunk.__getitem__)
        for index in sorted({low, high}):
            points.append({'t': round((sample_offset + start + index) / rate, 6),
                           'v': round(chunk[index], 6)})
    return points

"""单路ECG切拍的无拟合形态特征；只使用本拍与历史RR。"""
import numpy as np


def extract_features(x, rr):
    """输入既有144Hz/128点归一化切拍，R位于51.2；不接收身份或标签。"""
    x = np.asarray(x, dtype=np.float64)
    rr = np.asarray(rr, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != 128 or rr.shape != (len(x), 3):
        raise ValueError('切拍或RR形状不符')
    if not np.isfinite(x).all() or not np.isfinite(rr).all():
        raise ValueError('非有限输入')
    # 局部最大绝对偏转固定极性；绝对值相同时argmax取最早位置。
    local = x[:, 44:60]
    peak = np.argmax(np.abs(local), axis=1) + 44
    sign = np.where(x[np.arange(len(x)), peak] < 0, -1., 1.)
    z = x * sign[:, None]
    columns, names = [rr], ['rr_pre_80', 'rr_pre_400', 'rr_80_400']
    def add(values, labels):
        a = np.asarray(values)
        columns.append(a[:, None] if a.ndim == 1 else a)
        names.extend(labels)
    add(z.reshape(-1, 32, 4).mean(2), [f'mean4_{i}' for i in range(32)])
    # Haar块均值/差值只需加减移位；不从全体数据学习小波或PCA。
    blocks = z.reshape(-1, 16, 8)
    add(blocks[:, :, :4].mean(2) - blocks[:, :, 4:].mean(2), [f'haar8_{i}' for i in range(16)])
    for label, lo, hi in [('pre', 8, 40), ('qrs', 40, 66), ('post', 66, 104), ('tail', 104, 128)]:
        a = z[:, lo:hi]
        values = np.stack([a.mean(1), a.min(1), a.max(1), np.mean(a*a, 1),
                           np.mean(np.abs(np.diff(a, axis=1)), 1)], axis=1)
        add(values, [f'{label}_{s}' for s in ['mean', 'min', 'max', 'energy', 'variation']])
    q = z[:, 40:66]
    amplitude = np.max(np.abs(q), axis=1)
    # 宽度是固定区域超过半峰的点数，不是临床标注QRS时限。
    add(np.sum(np.abs(q) >= .5 * amplitude[:, None], axis=1) / 144., ['half_peak_occupancy_seconds'])
    add((peak - 51.2) / 144., ['local_peak_offset_seconds'])
    add(np.max(z, axis=1) - np.min(z, axis=1), ['range_normalized'])
    features = np.concatenate(columns, axis=1).astype(np.float32)
    if features.shape[1] != len(names) or not np.isfinite(features).all():
        raise ValueError('特征无效')
    return features, names

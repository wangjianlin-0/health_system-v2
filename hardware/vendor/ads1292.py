"""ADS1292R离线解码；保留24位码，不推断采样率、导联或物理单位。

依据及格式版本见docs/ads1292.md。不打开SPI/串口，不驱动板卡。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SpiSample:
    status: int
    loff_bits: int
    gpio_bits: int
    ch1: int
    ch2: int


def signed24(data: bytes) -> int:
    """三个大端二进制补码字节转Python整数，拒绝截断或补齐。"""
    if len(data) != 3:
        raise ValueError('24位通道必须恰为3字节')
    return int.from_bytes(data, 'big', signed=True)


def decode_spi_frame(frame: bytes) -> SpiSample:
    """解码一个已按DRDY/CS划界的9字节帧；状态位不等于已验证的脱落状态。"""
    if len(frame) != 9:
        raise ValueError('SPI帧必须恰为9字节')
    status = int.from_bytes(frame[:3], 'big')
    if status >> 20 != 0xC or status & 0x1FFF:
        raise ValueError('SPI状态固定前缀或保留位错误')
    return SpiSample(status, (status >> 15) & 31, (status >> 13) & 3,
                     signed24(frame[3:6]), signed24(frame[6:9]))


VENDOR_FORMATS = {'source_10': 1, 'document_34': 4}


def decode_vendor_frame(frame: bytes, *, format: str) -> tuple[tuple[int, int], ...]:
    """解码已划界的厂商帧；格式必须显式选定，不扫描AA BB猜测同步。

    source_10对应附带main.c；document_34仅对应附带协议说明。
    每个4字节字为零扩展的24位偏移码，恢复后返回(CH1, CH2)。
    两种格式都不携带芯片状态、序号、校验或单位。
    """
    if format not in VENDOR_FORMATS:
        raise ValueError('格式须为source_10或document_34')
    count = VENDOR_FORMATS[format]
    if len(frame) != 2 + 8 * count or frame[:2] != b'\xaa\xbb':
        raise ValueError('厂商帧头或长度错误，不能自动混用协议版本')
    values = []
    for pos in range(2, len(frame), 4):
        word = int.from_bytes(frame[pos:pos + 4], 'big')
        if word > 0xFFFFFF:
            raise ValueError('偏移码的高8位必须为0，不是32位符号扩展')
        values.append(word - 0x800000)
    return tuple(zip(values[::2], values[1::2]))

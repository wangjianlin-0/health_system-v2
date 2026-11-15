"""Windows串口只收适配；标准库实现，无命令发送、清空接收缓冲或自动重连。"""
import ctypes as ct
import os
import re
import time


DWORD = ct.c_uint32
WORD = ct.c_uint16
BYTE = ct.c_ubyte


class DCB(ct.Structure):
    # 用一个DWORD容纳微软DCB的位域，避免依赖宿主C编译器位域规则。
    _fields_ = [('length', DWORD), ('baud', DWORD), ('flags', DWORD),
                ('reserved', WORD), ('xon_limit', WORD), ('xoff_limit', WORD),
                ('byte_size', BYTE), ('parity', BYTE), ('stop_bits', BYTE),
                ('xon', ct.c_char), ('xoff', ct.c_char), ('error', ct.c_char),
                ('eof', ct.c_char), ('event', ct.c_char), ('reserved1', WORD)]


class Timeouts(ct.Structure):
    _fields_ = [('interval', DWORD), ('read_multiplier', DWORD), ('read_constant', DWORD),
                ('write_multiplier', DWORD), ('write_constant', DWORD)]


class ComStat(ct.Structure):
    _fields_ = [('flags', DWORD), ('input_bytes', DWORD), ('output_bytes', DWORD)]


def kernel32():
    if os.name != 'nt':
        raise OSError('当前串口适配仅支持Windows；演示/回放可跨平台使用')
    api = ct.WinDLL('kernel32', use_last_error=True)
    signatures = {
        'CreateFileW': ([ct.c_wchar_p, DWORD, DWORD, ct.c_void_p, DWORD, DWORD, ct.c_void_p], ct.c_void_p),
        'GetCommState': ([ct.c_void_p, ct.POINTER(DCB)], ct.c_int),
        'SetCommState': ([ct.c_void_p, ct.POINTER(DCB)], ct.c_int),
        'SetCommTimeouts': ([ct.c_void_p, ct.POINTER(Timeouts)], ct.c_int),
        'ClearCommError': ([ct.c_void_p, ct.POINTER(DWORD), ct.POINTER(ComStat)], ct.c_int),
        'ReadFile': ([ct.c_void_p, ct.c_void_p, DWORD, ct.POINTER(DWORD), ct.c_void_p], ct.c_int),
        'CloseHandle': ([ct.c_void_p], ct.c_int),
    }
    for name, (args, result) in signatures.items():
        function = getattr(api, name)
        function.argtypes = args; function.restype = result
    return api


class WindowsSerial:
    """同步句柄配立即返回超时，每次读取上限4096字节；只供单一消费者调用。"""
    def __init__(self, port, baud=115200, *, api=None):
        if not isinstance(port, str) or not re.fullmatch(r'COM[1-9][0-9]{0,4}', port.upper()):
            raise ValueError('串口应为COM1、COM14等名称，不接受文件路径')
        if baud not in (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600):
            raise ValueError('不支持的波特率')
        self.port = port.upper(); self.baud = baud
        self.api = api if api is not None else kernel32()
        self.handle = None
        handle = self.api.CreateFileW('\\\\.\\' + self.port, 0xC0000000, 0, None, 3, 0, None)
        if handle is None or handle == ct.c_void_p(-1).value:
            self.fail('打开串口（检查端口号、占用与驱动）')
        self.handle = handle
        try:
            state = DCB(); state.length = ct.sizeof(state)
            self.check(self.api.GetCommState(handle, ct.byref(state)), '读取串口配置')
            state.baud = baud; state.byte_size = 8; state.parity = 0; state.stop_bits = 0
            # binary=1，其余为0：无流控、不剔除NUL、DTR/RTS禁用，不发复位脉冲。
            state.flags = 1
            state.reserved = state.reserved1 = 0
            self.check(self.api.SetCommState(handle, ct.byref(state)), '设置8N1/无流控')
            # MAXDWORD,0,0使ReadFile只取已有字节，即使无数据也立即返回。
            timeout = Timeouts(0xFFFFFFFF, 0, 0, 0, 0)
            self.check(self.api.SetCommTimeouts(handle, ct.byref(timeout)), '设置立即返回读取')
        except BaseException:
            self.close()
            raise

    def fail(self, action):
        code = ct.get_last_error() if os.name == 'nt' else 0
        raise OSError(code, f'{action}失败；Windows错误码={code}')

    def check(self, success, action):
        if not success:
            self.fail(action)

    def read(self, limit=4096):
        if self.handle is None:
            raise OSError('串口已关闭')
        if not isinstance(limit, int) or not 1 <= limit <= 4096:
            raise ValueError('读取上限须为1..4096字节')
        errors = DWORD(); status = ComStat()
        self.check(self.api.ClearCommError(self.handle, ct.byref(errors), ct.byref(status)), '检查串口状态')
        if errors.value:
            # 驱动错误没有可靠的丢样数量，停止保存错误，不能填成源样本丢弃。
            raise OSError(f'串口驱动错误 flags=0x{errors.value:X}；不推断丢样数量')
        if not status.input_bytes:
            return b''
        size = min(limit, status.input_bytes)
        buffer = ct.create_string_buffer(size); received = DWORD()
        self.check(self.api.ReadFile(self.handle, buffer, size, ct.byref(received), None), '读取串口')
        return buffer.raw[:received.value]

    def close(self):
        if self.handle is not None:
            handle, self.handle = self.handle, None
            self.check(self.api.CloseHandle(handle), '关闭串口')


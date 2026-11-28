"""网页与API同端口启动；模型在当前Python环境执行，数据保存在项目runtime。"""
import argparse
import errno
import os
from pathlib import Path
import socket
import sys
from threading import Thread
import webbrowser

import uvicorn

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'business_logic'))


def bind_socket(preferred_port: int, fallback: bool) -> socket.socket:
    last_port = min(preferred_port + 10, 65535) if fallback else preferred_port
    for port in range(preferred_port, last_port + 1):
        listener = socket.socket()
        try:
            if os.name == 'nt':
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', port))
        except OSError as error:
            listener.close()
            # Windows exclusive listeners can report access denied on a second bind.
            if error.errno != errno.EADDRINUSE and getattr(error, 'winerror', None) not in (10013, 10048):
                raise
            continue
        return listener
    ports = str(preferred_port) if last_port == preferred_port else f'{preferred_port}-{last_port}'
    raise SystemExit(f'Port unavailable ({ports}). Run start_pc.ps1 with a different -Port.')


class BrowserServer(uvicorn.Server):
    async def startup(self, sockets=None):
        await super().startup(sockets=sockets)
        if self.started:
            url = f'http://127.0.0.1:{self.config.port}/'
            Thread(target=webbrowser.open, args=(url,), daemon=True).start()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--open', action='store_true', help='Try the next 10 ports if needed and open the browser')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    if not (ROOT / 'frontend/dist/index.html').is_file():
        raise SystemExit('请先在frontend目录运行npm.cmd ci和npm.cmd run build')
    from ai_model.explanation.generator import _load_project_env
    from desktop_launcher import create_app

    with bind_socket(args.port, fallback=args.open) as listener:
        _load_project_env()
        report_provider = os.getenv('ECG_EXPLANATION_PROVIDER', 'template')
        print(f'Report explanation provider: {report_provider}', flush=True)
        port = listener.getsockname()[1]
        if port != args.port:
            print(f'Port {args.port} unavailable. Using port {port}.', flush=True)
        print(f'未卜心知：http://127.0.0.1:{port} · CNN/HGB电脑推理', flush=True)
        config = uvicorn.Config(create_app(), host='127.0.0.1', port=port)
        server = BrowserServer(config) if args.open else uvicorn.Server(config)
        server.run(sockets=[listener])
        if not server.started:
            raise SystemExit(1)


if __name__ == '__main__':
    main()

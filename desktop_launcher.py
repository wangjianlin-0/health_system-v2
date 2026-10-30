"""Local desktop launcher: bundled UI, API and offline ECG model."""
import os
import sys
from pathlib import Path

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / 'business_logic'))


def create_app():
    from app.services import migrations
    migrations.MIGRATIONS_DIR = ROOT / 'business_logic' / 'db' / 'migrations'
    from app.main import app
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
    front = ROOT / 'frontend' / 'dist'
    app.mount('/assets', StaticFiles(directory=front / 'assets'), name='assets')

    @app.get('/{path:path}', include_in_schema=False)
    def ui(path: str):
        if path == 'api' or path.startswith('api/'):
            raise HTTPException(status_code=404)
        return FileResponse(front / 'index.html')
    return app


def main():
    import argparse
    import logging
    import socket
    import threading
    import webbrowser
    import tkinter as tk
    from tkinter import messagebox
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--smoke-test', action='store_true')
    args = parser.parse_args()
    data = args.data_dir or Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'WeiBuXinZhi'
    data.mkdir(parents=True, exist_ok=True)
    # Keep records outside the temporary one-file extraction directory.
    os.environ['HEALTH_DB_PATH'] = str(data / 'health.sqlite3')
    os.environ['ECG_UPLOAD_DIR'] = str(data / 'uploads')
    os.environ['ECG_MODEL_TYPE'] = 'openecg'
    os.environ['ECG_EXPLANATION_PROVIDER'] = 'template'
    log = (data / 'desktop.log').open('a', encoding='utf-8', buffering=1)
    sys.stdout = sys.stderr = log
    logging.basicConfig(stream=log, level=logging.INFO)

    if args.smoke_test:
        import json
        from fastapi.testclient import TestClient
        app = create_app()
        with TestClient(app) as client:
            assert client.get('/').status_code == 200
            assert client.get('/records/test').status_code == 200
            assert client.get('/api/not-found').status_code == 404
            from signal_processing.python.ecg_preprocessing import parse_csv, process
            from ai_model.inference.openecg_adapter import OpenEcgClassifier
            signal = parse_csv((ROOT / 'csv/ptbxl_00001_lead_II_500Hz_10s.csv').read_text(), 500)
            result = OpenEcgClassifier().predict(process(signal))
            assert result['status'] == 'classified', result
            (data / 'smoke-test.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        return

    window = tk.Tk()
    window.title('未卜心知 · 心电分析')
    window.geometry('520x250')
    window.resizable(False, False)
    state = tk.StringVar(value='正在启动本地分析服务…')
    tk.Label(window, text='未卜心知 · 心电分析', font=('Microsoft YaHei', 18)).pack(pady=(20, 10))
    tk.Label(window, textvariable=state, wraplength=480).pack(pady=6)
    tk.Label(window, text='CSV 导入 → 毫伏换算 → 波形与本地 AI 分析\n关闭此窗口将停止服务；记录会保留。', font=('Microsoft YaHei', 10)).pack(pady=8)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    server = uvicorn.Server(uvicorn.Config(create_app(), host='127.0.0.1', port=port, log_config=None))
    errors = []

    def serve():
        try:
            server.run(sockets=[sock])
        except BaseException as error:
            logging.exception('Desktop service failed')
            errors.append(str(error))

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    button = tk.Button(window, text='打开分析界面', state='disabled', command=lambda: webbrowser.open(url))
    button.pack(pady=6)

    def ready():
        if server.started:
            state.set(f'服务已就绪 · {url}')
            button.config(state='normal')
            webbrowser.open(url)
        elif not worker.is_alive():
            state.set('启动失败，请查看数据目录内 desktop.log')
            messagebox.showerror('启动失败', '\n'.join(errors) or str(data / 'desktop.log'))
        else:
            window.after(200, ready)

    def close():
        button.config(state='disabled')
        state.set('正在保存并停止服务…')
        server.should_exit = True
        if worker.is_alive():
            window.after(200, close)
        else:
            sock.close()
            window.destroy()

    window.protocol('WM_DELETE_WINDOW', close)
    window.after(200, ready)
    window.mainloop()


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        if '--smoke-test' not in sys.argv:
            from tkinter import messagebox
            messagebox.showerror('未卜心知启动失败', traceback.format_exc())
        sys.exit(1)

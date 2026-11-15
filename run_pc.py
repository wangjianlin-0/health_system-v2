"""网页与API同端口启动；模型在当前Python环境执行，数据保存在项目runtime。"""
from pathlib import Path
import argparse
import os
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'business_logic'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if not (ROOT / 'frontend/dist/index.html').is_file():
        raise SystemExit('请先在frontend目录运行npm.cmd ci和npm.cmd run build')
    os.environ.setdefault('ECG_EXPLANATION_PROVIDER', 'template')
    from desktop_launcher import create_app
    import uvicorn
    print(f'未卜心知：http://127.0.0.1:{args.port} · CNN/HGB电脑推理')
    uvicorn.run(create_app(), host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()

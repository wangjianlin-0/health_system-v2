"""本地Chrome无头验收：独立数据库，真实网页上传和CPU模型，不访问采集硬件。"""
from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    from playwright.sync_api import sync_playwright
    folder = ROOT / 'runtime/verification' / ('browser-' + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    env = dict(os.environ, HEALTH_DB_PATH=str(folder / 'test.sqlite3'),
               ECG_UPLOAD_DIR=str(folder / 'uploads'), ECG_EXPLANATION_PROVIDER='template')
    python = os.environ.get('ECG_PC_PYTHON', 'E:/Environments/Python/pytorch/Scripts/python.exe')
    log = (folder / 'server.log').open('w', encoding='utf-8')
    server = subprocess.Popen([python, '-X', 'utf8', 'run_pc.py', '--port', str(port)],
        cwd=ROOT, env=env, stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    errors = []
    try:
        import urllib.request
        for _ in range(100):
            try:
                urllib.request.urlopen(base, timeout=1)
                break
            except OSError:
                time.sleep(.1)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
            page.on('pageerror', lambda error: errors.append(str(error)))
            data = dict(username='browser-' + uuid.uuid4().hex[:8], password='browser-test-password')
            assert page.request.post(base + '/api/v1/auth/register', data=data).ok
            page.goto(base)
            page.get_by_label('用户名').fill(data['username'])
            page.get_by_label('密码（至少 8 位）').fill(data['password'])
            page.get_by_role('button', name='登录', exact=True).click()
            page.get_by_role('link', name='实时监测', exact=True).click()
            page.get_by_role('heading', name='实时心电监测').wait_for()
            page.get_by_text('等待连接', exact=True).wait_for()
            assert page.locator('aside').count() == 0
            page.screenshot(path=str(folder / 'monitor-desktop.png'), full_page=True)
            page.reload()
            page.get_by_role('heading', name='实时心电监测').wait_for()
            page.get_by_role('link', name='导入与分析', exact=True).click()
            page.locator('input[type=file]').set_input_files(str(ROOT / 'ai_model/vendor/ecg_edge/model/inference/examples/synthetic500.csv'))
            page.get_by_role('button', name='导入并分析', exact=True).click()
            page.wait_for_url('**/records/*', timeout=45000)
            page.get_by_text('CNN-H27-fold0', exact=False).first.wait_for()
            page.get_by_role('columnheader', name='R 峰时间').wait_for()
            page.screenshot(path=str(folder / 'cnn-record.png'), full_page=True)
            page.get_by_role('button', name='导出心电图片', exact=True).click()
            dialog = page.get_by_role('dialog', name='导出心电图片')
            preview = dialog.get_by_role('img')
            preview.wait_for()
            dialog.get_by_text('第 1 / 2 页', exact=True).wait_for()
            page.screenshot(path=str(folder / 'ecg-export-desktop.png'), full_page=True)
            with page.expect_download() as download:
                dialog.get_by_role('button', name='下载第 1 页 PNG').click()
            png_path = folder / 'ecg-paper-page-1.png'
            download.value.save_as(png_path)
            # Verify the actual downloaded PNG dimensions, physical print scale and all chunk CRCs.
            import struct, zlib
            content = png_path.read_bytes()
            assert content[:8] == b'\x89PNG\r\n\x1a\n'
            offset, physical = 8, 0
            while offset < len(content):
                length = struct.unpack('>I', content[offset:offset + 4])[0]
                kind = content[offset + 4:offset + 8]
                payload = content[offset + 8:offset + 8 + length]
                assert zlib.crc32(kind + payload) == struct.unpack('>I', content[offset + 8 + length:offset + 12 + length])[0]
                if kind == b'IHDR': assert struct.unpack('>II', payload[:8]) == (2376, 1680)
                if kind == b'pHYs':
                    assert struct.unpack('>IIB', payload) == (8000, 8000, 1)
                    physical += 1
                offset += length + 12
            assert physical == 1
            dialog.get_by_role('button', name='下一页', exact=True).click()
            dialog.get_by_role('button', name='下载第 2 页 PNG').wait_for(state='visible')
            preview.wait_for()
            dialog.get_by_label('走纸速度').select_option('50')
            dialog.get_by_text('第 1 / 4 页', exact=True).wait_for()
            preview.wait_for()
            dialog.locator('select').nth(1).select_option('20')
            preview.wait_for()
            dialog.locator('select').nth(1).select_option('5')
            preview.wait_for()
            dialog.locator('select').nth(2).select_option('filtered')
            preview.wait_for()
            dialog.get_by_label('开始时间（秒）').fill('12.5')
            dialog.get_by_label('结束时间（秒）').fill('18.5')
            dialog.get_by_text('第 1 / 1 页', exact=True).wait_for()
            preview.wait_for()
            page.set_viewport_size({'width': 390, 'height': 844})
            page.screenshot(path=str(folder / 'ecg-export-mobile.png'), full_page=True)
            assert dialog.evaluate('(el) => el.scrollWidth <= el.clientWidth'), 'export mobile overflow'
            dialog.get_by_label('结束时间（秒）').fill('1')
            dialog.get_by_role('alert').wait_for()
            assert dialog.get_by_role('button', name='下载第 1 页 PNG').is_disabled()
            dialog.get_by_role('button', name='关闭心电图片导出').click()
            page.set_viewport_size({'width': 1440, 'height': 1000})
            page.get_by_label('重新分析使用的模型').select_option('hgb')
            page.get_by_role('button', name='重新分析', exact=True).click()
            page.wait_for_url('**/analyze?task=*')
            page.wait_for_url('**/records/*', timeout=45000)
            page.get_by_text('HGB-v92-fold0', exact=False).first.wait_for()
            page.screenshot(path=str(folder / 'hgb-record.png'), full_page=True)
            page.get_by_role('link', name='实时监测', exact=True).click()
            page.set_viewport_size({'width': 390, 'height': 844})
            page.screenshot(path=str(folder / 'monitor-mobile.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'mobile overflow'
            assert not errors, errors
            browser.close()
        (folder / 'result.json').write_text(json.dumps(dict(passed=True, page_errors=errors,
            tested=['login', 'monitor without top notice', 'reload', 'real CNN upload', 'HGB reanalysis',
                    'PNG download/dimensions/physical scale/CRC', 'paper pagination/speed/gain/filter/time range',
                    'invalid range rejected', '390px responsive/export dialog']), indent=2), encoding='utf-8')
        print(folder)
    finally:
        server.terminate()
        server.wait(timeout=10)
        log.close()


if __name__ == '__main__':
    main()

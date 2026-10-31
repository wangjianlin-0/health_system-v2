"""命令行备份：从仓库根目录运行。"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'business_logic'))


def main() -> int:
    parser = argparse.ArgumentParser(description='备份 health.sqlite3 到 runtime/backups')
    parser.add_argument('--target', default=None, help='备份目录（默认 runtime/backups）')
    parser.add_argument('--keep', type=int, default=10, help='保留最近 N 份，0 表示不清理')
    args = parser.parse_args()
    from app.services.backup import backup_database

    result = backup_database(args.target, args.keep)
    print(f"备份完成：{result['path']}")
    print(f"记录数：{result['records']}；大小：{result['bytes'] / 1024:.1f} KB；校验：{result['integrity']}")
    if result['removed']:
        print('已清理：' + ', '.join(result['removed']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

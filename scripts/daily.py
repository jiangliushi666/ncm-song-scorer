"""每日采集脚本：适合 Windows 任务计划程序 / cron 定时执行.

用法（在项目根目录）:
    python scripts/daily.py                 # 默认 ncm_scorer.db
    python scripts/daily.py --db /path/db   # 指定数据库

Windows 任务计划：schtasks /create /tn ncm-scorer-daily ^
    /tr "python C:\\path\\to\\ncm-song-scorer\\scripts\\daily.py" /sc daily /st 09:00
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ncm_scorer.api import NcmClient          # noqa: E402
from ncm_scorer.pipeline import run_daily     # noqa: E402
from ncm_scorer.storage import Store          # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="ncm-scorer 每日采集")
    parser.add_argument("--db", default="ncm_scorer.db")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    store = Store(args.db)
    try:
        stats = run_daily(NcmClient(), store)
        print(stats)
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())

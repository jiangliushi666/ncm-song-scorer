"""命令行入口: python -m ncm_scorer <command>."""

from __future__ import annotations

import argparse
import logging
import sys

from . import __version__
from .api import NcmClient
from .storage import Store

DEFAULT_DB = "ncm_scorer.db"
MODEL_FILE = "model.pkl"


def _fmt_rows(rows, columns, headers):
    widths = [max(len(h), *(len(str(r.get(c, ""))) for r in rows)) if rows else len(h)
              for c, h in zip(columns, headers)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    out = [line, "-" * len(line)]
    for r in rows:
        out.append("  ".join(str(r.get(c, "")).ljust(w)
                             for c, w in zip(columns, widths)))
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="ncm-scorer", description="网易云音乐新歌自动评分系统"
    )
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 数据库路径")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("daily", help="每日例行：拉榜+发现新歌+快照+打分")
    sub.add_parser("charts", help="仅拉取新歌榜并入库")
    sub.add_parser("snapshot", help="对已跟踪歌曲拍互动快照")
    sub.add_parser("score", help="对已跟踪歌曲启发式打分")
    p_train = sub.add_parser("train", help="训练 ML 模型（需先攒 2-3 周数据）")
    p_train.add_argument("--horizon-days", type=float, default=14.0)
    p_top = sub.add_parser("top", help="输出当前 Top N 排名")
    p_top.add_argument("-n", type=int, default=20)
    p_top.add_argument("--model", action="store_true",
                       help="用 ML 模型分（默认启发式分）")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    store = Store(args.db)
    try:
        if args.cmd == "daily":
            from .pipeline import run_daily
            stats = run_daily(NcmClient(), store)
            print("daily 完成:", stats)
            for t in stats.get("top5", []):
                print(f"  {t['score']:>5}  {t['name']} - {t['artists']}")
        elif args.cmd == "charts":
            from .pipeline import fetch_chart_and_discover
            print(fetch_chart_and_discover(NcmClient(), store))
        elif args.cmd == "snapshot":
            from .pipeline import take_snapshots
            ids = store.tracked_song_ids(max_age_days=60)[:200]
            print(take_snapshots(NcmClient(), store, ids))
        elif args.cmd == "score":
            from .pipeline import score_all
            results = score_all(store, store.tracked_song_ids(max_age_days=60)[:200])
            for r in results[:20]:
                print(f"{r['score']:>5}  {r['name']} - {r['artists']}")
        elif args.cmd == "top":
            rows = store.latest_scores(limit=args.n)
            print(_fmt_rows(
                rows, ["score", "name", "artists"],
                ["SCORE", "SONG", "ARTISTS"],
            ))
        elif args.cmd == "train":
            from .model import train
            print(train(store, horizon_days=args.horizon_days,
                        model_path=MODEL_FILE))
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"错误: {e}", file=sys.stderr)
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())

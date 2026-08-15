"""把当前排名生成单文件静态页 index.html（供 GitHub Pages 发布）.

用法: python scripts/build_site.py [--db ncm_scorer.db] [--out site/index.html] [--top 50]
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ncm_scorer.storage import Store  # noqa: E402

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ncm-scorer · 网易云新歌爆款潜力榜</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{
    font-family: system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
    max-width: 760px; margin: 0 auto; padding: 24px 16px 64px;
    line-height: 1.6;
  }}
  h1 {{ font-size: 1.4em; margin-bottom: 4px; }}
  .meta {{ color: #888; font-size: .85em; margin-bottom: 20px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .95em; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #8884; }}
  th {{ position: sticky; top: 0; background: inherit; backdrop-filter: blur(4px); }}
  td.score {{ font-variant-numeric: tabular-nums; font-weight: 600; }}
  tr.top3 td.score {{ color: #e6a817; }}
  .bar {{ display: inline-block; height: 6px; border-radius: 3px;
         background: linear-gradient(90deg,#4a9,#2c7); vertical-align: middle; }}
  .foot {{ color: #888; font-size: .8em; margin-top: 28px; }}
  a {{ color: #2b7; }}
</style>
</head>
<body>
<h1>🎵 网易云新歌爆款潜力榜</h1>
<div class="meta">更新于 {updated} · 数据源：网易云音乐新歌榜 · 由 GitHub Actions 每日自动更新</div>
<table>
<thead><tr><th>#</th><th style="width:14%">分数</th><th>歌曲</th><th>歌手</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<div class="foot">
  分数 0-100，启发式模型 heuristic-v1（讨论密度 40% + 平台热度 25% + 评论增速 20% + 歌手资历 15%）。
  仅个人研究用途，数据归网易云音乐所有。
  项目：<a href="https://github.com/jiangliushi666/ncm-song-scorer">ncm-song-scorer</a>
</div>
<script type="application/ld+json">{ldjson}</script>
</body>
</html>
"""


def build(db_path: str, out_path: str, top_n: int = 50) -> int:
    store = Store(db_path)
    try:
        rows = store.latest_scores(limit=top_n)
    finally:
        store.close()
    if not rows:
        raise SystemExit("数据库中还没有打分记录，先运行 daily")

    trs = []
    for i, r in enumerate(rows, start=1):
        name = html.escape(str(r.get("name") or ""))
        artists = html.escape(str(r.get("artists") or ""))
        score = float(r.get("score") or 0)
        cls = ' class="top3"' if i <= 3 else ""
        trs.append(
            f'<tr{cls}><td>{i}</td><td class="score">{score:.1f} '
            f'<span class="bar" style="width:{score * 0.9:.0f}px"></span></td>'
            f"<td>{name}</td><td>{artists}</td></tr>"
        )
    updated = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    page = TEMPLATE.format(
        updated=updated,
        rows="\n".join(trs),
        ldjson=json.dumps(
            {"name": "ncm-scorer ranking", "updated": updated,
             "top1": rows[0].get("name")},
            ensure_ascii=False,
        ),
    )
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"site written: {out_path} ({len(rows)} rows)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="ncm_scorer.db")
    parser.add_argument("--out", default="site/index.html")
    parser.add_argument("--top", type=int, default=50)
    args = parser.parse_args()
    return build(args.db, args.out, args.top)


if __name__ == "__main__":
    raise SystemExit(main())

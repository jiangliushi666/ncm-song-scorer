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
  button.play {{
    border: 1px solid #8886; background: transparent; color: inherit;
    border-radius: 50%; width: 28px; height: 28px; cursor: pointer;
    font-size: 12px; line-height: 1;
  }}
  button.play:hover {{ border-color: #2b7; color: #2b7; }}
  #player-box iframe {{ display: block; border-radius: 8px; margin-bottom: 14px; }}
  .bar {{ display: inline-block; height: 6px; border-radius: 3px;
         background: linear-gradient(90deg,#4a9,#2c7); vertical-align: middle; }}
  .foot {{ color: #888; font-size: .8em; margin-top: 28px; }}
  a {{ color: #2b7; }}
</style>
</head>
<body>
<h1>🎵 网易云新歌爆款潜力榜</h1>
<div class="meta">更新于 {updated} · 打分模型：{model} · 数据源：网易云音乐新歌榜 · 由 GitHub Actions 每日自动更新</div>
<div id="player-box" hidden></div>
<table>
<thead><tr><th>#</th><th style="width:14%">分数</th><th>歌曲</th><th>歌手</th><th>发布日期</th><th>采集时间</th><th></th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<div class="foot">
  分数 0-100，启发式模型 heuristic-v1（讨论密度 40% + 平台热度 25% + 评论增速 20% + 歌手资历 15%）。
  ▶ 为页面内试听，版权/VIP 歌曲为片段；点击<b>歌名</b>跳转网易云音乐可完整播放（登录态）。
  仅个人研究用途，数据归网易云音乐所有。
  项目：<a href="https://github.com/jiangliushi666/ncm-song-scorer">ncm-song-scorer</a>
</div>
<script>
  var box = document.getElementById('player-box');
  var current = null;
  document.addEventListener('click', function (e) {{
    var btn = e.target.closest('button.play');
    if (!btn) return;
    var id = btn.getAttribute('data-id');
    if (current === id) {{ box.hidden = !box.hidden; return; }}
    current = id;
    box.hidden = false;
    box.innerHTML = '<iframe frameborder="no" border="0" marginwidth="0" marginheight="0" ' +
      'width="100%" height="86" src="https://music.163.com/outchain/player?type=2&id=' +
      id + '&auto=1&height=66"></iframe>';
    box.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
  }});
</script>
<script type="application/ld+json">{ldjson}</script>
</body>
</html>
"""


def _fmt_publish(ms) -> str:
    if not ms:
        return "—"
    return time.strftime("%Y-%m-%d", time.gmtime(int(ms) / 1000))


def _fmt_collected(ts) -> str:
    if not ts:
        return "—"
    return time.strftime("%m-%d %H:%M", time.gmtime(int(ts)))


def build(db_path: str, out_path: str, top_n: int = 50) -> int:
    store = Store(db_path)
    try:
        # 优先展示已训练 ML 分数；尚无模型时回退启发式基线
        rows = store.latest_scores(model_version="gbc-v1", limit=top_n)
        model_label = "ML 模型 gbc-v1（进入新歌榜概率）"
        if not rows:
            rows = store.latest_scores(model_version="heuristic-v1", limit=top_n)
            model_label = "启发式 heuristic-v1（未训练，冷启动基线）"
    finally:
        store.close()
    if not rows:
        raise SystemExit("数据库中还没有打分记录，先运行 daily")

    trs = []
    for i, r in enumerate(rows, start=1):
        song_id = int(r.get("song_id") or 0)
        name = html.escape(str(r.get("name") or ""))
        artists = html.escape(str(r.get("artists") or ""))
        score = float(r.get("score") or 0)
        published = html.escape(_fmt_publish(r.get("publish_time")))
        collected = html.escape(_fmt_collected(r.get("ts")))
        cls = ' class="top3"' if i <= 3 else ""
        song_link = (
            f'<a href="https://music.163.com/song?id={song_id}" '
            f'target="_blank" rel="noopener">{name}</a>'
        )
        play_btn = (
            f'<button class="play" data-id="{song_id}" '
            f'aria-label="播放 {name}" '
            f'title="页面内试听（版权/VIP 歌曲为片段）">▶</button>'
        )
        trs.append(
            f'<tr{cls}><td>{i}</td><td class="score">{score:.1f} '
            f'<span class="bar" style="width:{score * 0.9:.0f}px"></span></td>'
            f"<td>{song_link}</td><td>{artists}</td>"
            f"<td>{published}</td><td>{collected}</td><td>{play_btn}</td></tr>"
        )
    updated = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    page = TEMPLATE.format(
        updated=updated,
        model=model_label,
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

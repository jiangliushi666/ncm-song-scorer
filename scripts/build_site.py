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

from ncm_scorer.features import title_flags  # noqa: E402
from ncm_scorer.storage import Store  # noqa: E402

PARTS = (
    ("density", "讨论密度"),
    ("pop", "平台热度"),
    ("velocity", "评论增速"),
    ("artist", "歌手资历"),
    ("artist_heat", "上榜热"),
)

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
    max-width: 860px; margin: 0 auto; padding: 24px 16px 64px;
    line-height: 1.6;
  }}
  h1 {{ font-size: 1.4em; margin-bottom: 4px; }}
  .meta {{ color: #888; font-size: .85em; margin-bottom: 14px; }}
  .filters {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }}
  .filters button {{
    border: 1px solid #8886; background: transparent; color: inherit;
    border-radius: 999px; padding: 4px 12px; cursor: pointer; font-size: .85em;
  }}
  .filters button.on {{ border-color: #2b7; color: #2b7; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .95em; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #8884; }}
  th {{ position: sticky; top: 0; background: inherit; backdrop-filter: blur(4px); }}
  td.score {{ font-variant-numeric: tabular-nums; font-weight: 600; }}
  tr.top3 td.score {{ color: #e6a817; }}
  tr.song {{ cursor: pointer; }}
  tr.song:hover {{ background: #8881; }}
  tr.hidden {{ display: none; }}
  .badge {{
    display: inline-block; font-size: .7em; font-weight: 600;
    border: 1px solid #8886; border-radius: 4px; padding: 0 5px;
    margin-left: 6px; color: #888; vertical-align: middle;
  }}
  button.play {{
    border: 1px solid #8886; background: transparent; color: inherit;
    border-radius: 50%; width: 28px; height: 28px; cursor: pointer;
    font-size: 12px; line-height: 1;
  }}
  button.play:hover {{ border-color: #2b7; color: #2b7; }}
  .badge.vip {{ border-color: #c90; color: #c90; }}
  #player-box {{ margin-bottom: 14px; padding: 10px 12px; border: 1px solid #8884; border-radius: 10px; }}
  #player-box audio {{ width: 100%; display: block; }}
  .play-title {{ font-weight: 600; margin-bottom: 8px; }}
  .play-hint {{ font-size: .85em; color: #888; margin-top: 8px; }}
  .bar {{ display: inline-block; height: 6px; border-radius: 3px;
         background: linear-gradient(90deg,#4a9,#2c7); vertical-align: middle; }}
  .parts {{ display: flex; flex-wrap: wrap; gap: 10px 16px; font-size: .85em; color: #888; }}
  .parts b {{ color: inherit; font-variant-numeric: tabular-nums; }}
  .foot {{ color: #888; font-size: .8em; margin-top: 28px; }}
  a {{ color: #2b7; }}
</style>
</head>
<body>
<h1>🎵 网易云新歌爆款潜力榜</h1>
<div class="meta">更新于 {updated} · 打分模型：{model} · 数据源：网易云音乐新歌榜 · 由 GitHub Actions 每日自动更新</div>
<div class="filters" id="filters">
  <button type="button" data-filter="all" class="on">全部</button>
  <button type="button" data-filter="studio">隐藏 Live</button>
  <button type="button" data-filter="week">近 7 天</button>
</div>
<div id="player-box" hidden></div>
<table>
<thead><tr><th>#</th><th style="width:14%">分数</th><th>歌曲</th><th>歌手</th><th>发布日期</th><th>采集时间</th><th></th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<div class="foot">
  {foot}
  ▶ 点按钮在本页播放。点击行可展开分项明细。仅个人研究用途，数据归网易云音乐所有。
  项目：<a href="https://github.com/jiangliushi666/ncm-song-scorer">ncm-song-scorer</a>
</div>
<script>
  var box = document.getElementById('player-box');
  var current = null;
  var PLAY_API = {play_api};
  function fail(name, id) {{
    box.innerHTML = '<div class="play-title"></div><div class="play-hint">这首没有页内试听地址。</div>';
    box.querySelector('.play-title').textContent = name || ('歌曲 ' + id);
  }}
  function showAudio(url, name, id, onFail) {{
    box.innerHTML = '<div class="play-title"></div><audio controls autoplay preload="auto"></audio>';
    box.querySelector('.play-title').textContent = name || ('歌曲 ' + id);
    var a = box.querySelector('audio');
    a.src = url;
    a.onerror = function () {{ if (onFail) onFail(); }};
  }}
  function playSong(id, name) {{
    box.hidden = false;
    box.innerHTML = '<div class="play-title"></div><div class="play-hint">正在取播放地址…</div>';
    box.querySelector('.play-title').textContent = name || ('歌曲 ' + id);
    // 国内打不开 workers.dev；外链由浏览器直连 music.163.com，用听的人自己的 IP 取 CDN。
    var outer = 'https://music.163.com/song/media/outer/url?id=' + id + '.mp3';
    showAudio(outer, name, id, function () {{
      if (!PLAY_API) {{ fail(name, id); return; }}
      fetch(PLAY_API + (PLAY_API.indexOf('?') >= 0 ? '&' : '?') + 'id=' + id)
        .then(function (r) {{ return r.json(); }})
        .then(function (j) {{
          if (j && j.url) showAudio(j.url, name, id, function () {{ fail(name, id); }});
          else fail(name, id);
        }})
        .catch(function () {{ fail(name, id); }});
    }});
    box.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
  }}
  document.addEventListener('click', function (e) {{
    var btn = e.target.closest('button.play');
    if (btn) {{
      e.stopPropagation();
      var id = btn.getAttribute('data-id');
      if (current === id) {{ box.hidden = !box.hidden; return; }}
      current = id;
      playSong(id, btn.getAttribute('data-name') || '');
      return;
    }}
    if (e.target.closest('a')) return;
    var song = e.target.closest('tr.song');
    if (!song) return;
    var next = song.nextElementSibling;
    if (next && next.classList.contains('detail')) next.hidden = !next.hidden;
  }});
  var filter = 'all';
  document.getElementById('filters').addEventListener('click', function (e) {{
    var b = e.target.closest('button[data-filter]');
    if (!b) return;
    filter = b.getAttribute('data-filter');
    Array.prototype.forEach.call(document.querySelectorAll('#filters button'), function (x) {{
      x.classList.toggle('on', x === b);
    }});
    Array.prototype.forEach.call(document.querySelectorAll('tr.song'), function (tr) {{
      var live = tr.getAttribute('data-live') === '1';
      var age = Number(tr.getAttribute('data-age') || 999);
      var hide = (filter === 'studio' && live) || (filter === 'week' && age > 7);
      tr.classList.toggle('hidden', hide);
      var d = tr.nextElementSibling;
      if (d && d.classList.contains('detail')) {{
        d.classList.toggle('hidden', hide);
        if (hide) d.hidden = true;
      }}
    }});
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


def _age_days(publish_ms) -> int:
    if not publish_ms:
        return 999
    return max(int((time.time() - int(publish_ms) / 1000.0) / 86400), 0)


def _parse_detail(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}


def _pick_rows(store: Store, top_n: int):
    choices = (
        ("gbc-v1", "ML 模型 gbc-v1（新歌榜前 20 概率）",
         "分数 0-100，机器学习模型 gbc-v1（标签 = 新歌榜最佳名次 ≤ 20）。"),
        ("heuristic-v2", "启发式 heuristic-v2（Live 降权 + 歌手上榜热）",
         "分数 0-100，启发式 heuristic-v2（讨论密度 36% + 平台热度 22% + 评论增速 18% + 歌手资历 12% + 上榜热 12%；Live/翻唱 ×0.78）。"),
        ("heuristic-v1", "启发式 heuristic-v1（未训练，冷启动基线）",
         "分数 0-100，启发式模型 heuristic-v1（讨论密度 40% + 平台热度 25% + 评论增速 20% + 歌手资历 15%）。"),
    )
    for version, label, foot in choices:
        rows = store.latest_scores(model_version=version, limit=top_n)
        if rows:
            return rows, label, foot
    return [], "", "数据库中还没有打分记录。"


DEFAULT_PLAY_API = "https://ncm-scorer-play.2383566697.workers.dev/"


def build(db_path: str, out_path: str, top_n: int = 50,
          play_api: str = DEFAULT_PLAY_API) -> int:
    store = Store(db_path)
    try:
        rows, model_label, foot = _pick_rows(store, top_n)
    finally:
        store.close()
    if not rows:
        raise SystemExit("数据库中还没有打分记录，先运行 daily")

    trs = []
    for i, r in enumerate(rows, start=1):
        song_id = int(r.get("song_id") or 0)
        name = str(r.get("name") or "")
        artists = html.escape(str(r.get("artists") or ""))
        score = float(r.get("score") or 0)
        published = html.escape(_fmt_publish(r.get("publish_time")))
        collected = html.escape(_fmt_collected(r.get("ts")))
        flags = title_flags(name)
        is_live = flags["is_live"] or bool(_parse_detail(r.get("detail")).get("is_live"))
        age = _age_days(r.get("publish_time"))
        fee = r.get("fee")
        is_vip = fee is not None and int(fee) > 0
        badges = []
        if is_live:
            badges.append('<span class="badge">Live</span>')
        if is_vip:
            badges.append('<span class="badge vip">VIP</span>')
        badge = "".join(badges)
        cls = ' class="song top3"' if i <= 3 else ' class="song"'
        song_link = (
            f'<a href="https://music.163.com/song?id={song_id}" '
            f'target="_blank" rel="noopener">{html.escape(name)}</a>{badge}'
        )
        play_title = "本页播放"
        play_btn = (
            f'<button class="play" data-id="{song_id}" data-fee="{int(fee or 0)}" '
            f'data-name="{html.escape(name)}" '
            f'aria-label="播放 {html.escape(name)}" '
            f'title="{play_title}">▶</button>'
        )
        detail = _parse_detail(r.get("detail"))
        parts = []
        for key, label in PARTS:
            if key in detail:
                parts.append(f"{label} <b>{float(detail[key]):.1f}</b>")
        if detail.get("is_live"):
            parts.append(f"Live 降权 ×{detail.get('live_penalty', 0.78)}")
        parts_html = " · ".join(parts) or "暂无分项明细"
        trs.append(
            f'<tr{cls} data-live="{1 if is_live else 0}" data-age="{age}">'
            f'<td>{i}</td><td class="score">{score:.1f} '
            f'<span class="bar" style="width:{score * 0.9:.0f}px"></span></td>'
            f"<td>{song_link}</td><td>{artists}</td>"
            f"<td>{published}</td><td>{collected}</td><td>{play_btn}</td></tr>\n"
            f'<tr class="detail" hidden><td colspan="7"><div class="parts">{parts_html}</div></td></tr>'
        )
    updated = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    page = TEMPLATE.format(
        updated=updated,
        model=html.escape(model_label),
        play_api=json.dumps(play_api or ""),
        rows="\n".join(trs),
        foot=foot,
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
    parser.add_argument("--play-api", default=os.environ.get("PLAY_API", DEFAULT_PLAY_API),
                        help="官方播放地址代理（Cloudflare Worker）")
    args = parser.parse_args()
    return build(args.db, args.out, args.top, play_api=args.play_api)


if __name__ == "__main__":
    raise SystemExit(main())

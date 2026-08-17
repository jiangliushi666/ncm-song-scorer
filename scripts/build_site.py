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
  :root {{
    color-scheme: light dark;
    --bg: #f4f1ea;
    --card: #fffcf6;
    --ink: #1d1c19;
    --muted: #6f6b62;
    --line: #e4dfd4;
    --accent: #1a7f56;
    --gold: #b8860b;
    --vip: #b26a00;
    --shadow: 0 10px 30px #1d1c1912;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #161513;
      --card: #1f1e1b;
      --ink: #f3efe6;
      --muted: #a39d90;
      --line: #333029;
      --accent: #3dba84;
      --gold: #e0b84e;
      --vip: #e09a3e;
      --shadow: 0 10px 30px #0008;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    background: var(--bg);
    color: var(--ink);
    line-height: 1.55;
  }}
  .wrap {{
    width: min(920px, calc(100% - 32px));
    margin: 0 auto;
    padding: 28px 0 72px;
  }}
  .hero {{
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 20px;
    padding: 22px 22px 18px;
    box-shadow: var(--shadow);
  }}
  .kicker {{
    margin: 0 0 6px;
    color: var(--accent);
    font-size: .75em;
    letter-spacing: .12em;
    text-transform: uppercase;
  }}
  h1 {{
    margin: 0 0 8px;
    font-size: clamp(1.35rem, 4vw, 1.85rem);
    letter-spacing: -.02em;
  }}
  .meta {{ margin: 0; color: var(--muted); font-size: .88em; }}
  .toolbar {{
    display: flex;
    align-items: center;
    gap: 10px 18px;
    flex-wrap: wrap;
    margin: 16px 0 14px;
  }}
  .filter-group {{
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }}
  .filter-label {{ color: var(--muted); font-size: .82em; }}
  .filters {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .filters button {{
    border: 1px solid var(--line);
    background: var(--card);
    color: inherit;
    border-radius: 999px;
    padding: 6px 13px;
    cursor: pointer;
    font-size: .85em;
  }}
  .filters button.on {{
    border-color: var(--accent);
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 10%, var(--card));
  }}
  #player-box {{
    position: sticky;
    top: 8px;
    z-index: 5;
    margin-bottom: 14px;
    padding: 12px 14px;
    border: 1px solid var(--line);
    border-radius: 16px;
    background: var(--card);
    box-shadow: var(--shadow);
  }}
  #player-box audio {{ width: 100%; display: block; }}
  .play-title {{ font-weight: 650; margin-bottom: 8px; }}
  .play-hint {{ font-size: .85em; color: var(--muted); margin-top: 8px; }}
  .board {{
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 20px;
    overflow: hidden;
    box-shadow: var(--shadow);
  }}
  .board-head, .row {{
    display: grid;
    grid-template-columns: 44px 58px minmax(0, 1.4fr) minmax(0, .9fr) 108px 44px;
    gap: 8px;
    align-items: center;
    padding: 12px 16px;
  }}
  .board-head {{
    color: var(--muted);
    font-size: .78em;
    border-bottom: 1px solid var(--line);
    position: sticky;
    top: 0;
    background: var(--card);
    z-index: 2;
  }}
  .song {{
    border-bottom: 1px solid var(--line);
    cursor: pointer;
  }}
  .song:last-child {{ border-bottom: 0; }}
  .song:hover {{ background: color-mix(in srgb, var(--accent) 6%, var(--card)); }}
  .song.hidden {{ display: none; }}
  .c-rank, .c-score {{ font-variant-numeric: tabular-nums; }}
  .c-rank {{ color: var(--muted); font-weight: 650; }}
  .c-score {{ font-weight: 700; }}
  .top3 .c-rank, .top3 .c-score {{ color: var(--gold); }}
  .name {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    font-weight: 650;
  }}
  .name a {{ color: inherit; text-decoration: none; }}
  .name a:hover {{ color: var(--accent); }}
  .artists, .sub {{ color: var(--muted); font-size: .86em; }}
  .sub {{ display: none; margin-top: 4px; }}
  .c-date {{ color: var(--muted); font-size: .82em; }}
  .c-date .collected {{ display: block; }}
  .badge {{
    display: inline-block;
    font-size: .68em;
    font-weight: 700;
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 1px 7px;
    color: var(--muted);
  }}
  .badge.vip {{ border-color: var(--vip); color: var(--vip); }}
  button.play {{
    width: 36px;
    height: 36px;
    border: 0;
    border-radius: 50%;
    background: var(--accent);
    color: #fff;
    cursor: pointer;
    font-size: 13px;
  }}
  button.play:hover {{ filter: brightness(1.08); }}
  .detail {{
    padding: 0 16px 12px 16px;
    color: var(--muted);
  }}
  .parts {{ display: flex; flex-wrap: wrap; gap: 8px 14px; font-size: .85em; }}
  .parts b {{ color: var(--ink); font-variant-numeric: tabular-nums; }}
  .foot {{
    color: var(--muted);
    font-size: .8em;
    margin-top: 22px;
    max-width: 70ch;
  }}
  a {{ color: var(--accent); }}
  @media (max-width: 760px) {{
    .wrap {{ width: min(100% - 20px, 920px); padding-top: 16px; }}
    .hero, .board {{ border-radius: 16px; }}
    .board-head, .c-score, .c-artists, .c-date {{ display: none; }}
    .row {{
      grid-template-columns: 32px minmax(0, 1fr) 40px;
      padding: 12px;
    }}
    .sub {{ display: block; }}
    .detail {{ padding-left: 12px; padding-right: 12px; }}
  }}
</style>
</head>
<body>
<div class="wrap">
<header class="hero">
  <p class="kicker">ncm-scorer</p>
  <h1>新歌爆款潜力榜</h1>
  <p class="meta">更新于 {updated} · {model} · 数据来自网易云音乐新歌榜，每日自动更新</p>
</header>
<div class="toolbar" id="filters">
  <div class="filter-group" data-group="time">
    <span class="filter-label">发行</span>
    <div class="filters">
      <button type="button" data-time="all" class="on">本榜全部</button>
      <button type="button" data-time="week">近 7 天</button>
    </div>
  </div>
  <div class="filter-group" data-group="live">
    <span class="filter-label">类型</span>
    <div class="filters">
      <button type="button" data-live="all" class="on">含 Live</button>
      <button type="button" data-live="studio">不含 Live</button>
    </div>
  </div>
</div>
<div id="player-box" hidden></div>
<div class="board">
  <div class="board-head">
    <span>#</span><span>分数</span><span>歌曲</span><span>歌手</span><span>日期</span><span></span>
  </div>
  {rows}
</div>
<div class="foot">
  {foot}
  点 ▶ 在本页播放，点歌曲行可看分数构成。仅个人研究用途，数据归网易云音乐所有。
  项目：<a href="https://github.com/jiangliushi666/ncm-song-scorer">ncm-song-scorer</a>
</div>
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
    var song = e.target.closest('.song');
    if (!song) return;
    var detail = song.querySelector('.detail');
    if (detail) detail.hidden = !detail.hidden;
  }});
  var timeFilter = 'all';
  var liveFilter = 'all';
  function applyFilters() {{
    Array.prototype.forEach.call(document.querySelectorAll('.song'), function (card) {{
      var live = card.getAttribute('data-live') === '1';
      var age = Number(card.getAttribute('data-age') || 999);
      var hide = (timeFilter === 'week' && age > 7) || (liveFilter === 'studio' && live);
      card.classList.toggle('hidden', hide);
      var d = card.querySelector('.detail');
      if (d && hide) d.hidden = true;
    }});
  }}
  document.getElementById('filters').addEventListener('click', function (e) {{
    var timeBtn = e.target.closest('button[data-time]');
    var liveBtn = e.target.closest('button[data-live]');
    if (timeBtn) {{
      timeFilter = timeBtn.getAttribute('data-time');
      Array.prototype.forEach.call(document.querySelectorAll('button[data-time]'), function (x) {{
        x.classList.toggle('on', x === timeBtn);
      }});
    }} else if (liveBtn) {{
      liveFilter = liveBtn.getAttribute('data-live');
      Array.prototype.forEach.call(document.querySelectorAll('button[data-live]'), function (x) {{
        x.classList.toggle('on', x === liveBtn);
      }});
    }} else {{
      return;
    }}
    applyFilters();
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

    cards = []
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
        cls = "song top3" if i <= 3 else "song"
        play_btn = (
            f'<button class="play" data-id="{song_id}" data-fee="{int(fee or 0)}" '
            f'data-name="{html.escape(name)}" '
            f'aria-label="播放 {html.escape(name)}" title="本页播放">▶</button>'
        )
        detail = _parse_detail(r.get("detail"))
        parts = []
        for key, label in PARTS:
            if key in detail:
                parts.append(f"{label} <b>{float(detail[key]):.1f}</b>")
        if detail.get("is_live"):
            parts.append(f"Live 降权 ×{detail.get('live_penalty', 0.78)}")
        parts_html = " · ".join(parts) or "暂无分项明细"
        cards.append(
            f'<article class="{cls}" data-live="{1 if is_live else 0}" data-age="{age}">'
            f'<div class="row">'
            f'<div class="c-rank">{i}</div>'
            f'<div class="c-score">{score:.1f}</div>'
            f'<div class="c-song"><div class="name">'
            f'<a href="https://music.163.com/song?id={song_id}" target="_blank" '
            f'rel="noopener">{html.escape(name)}</a>{badge}</div>'
            f'<div class="sub">{artists} · {score:.1f} · {published}</div></div>'
            f'<div class="c-artists artists">{artists}</div>'
            f'<div class="c-date">{published}<span class="collected">采集 {collected}</span></div>'
            f'<div class="c-play">{play_btn}</div>'
            f'</div>'
            f'<div class="detail" hidden><div class="parts">{parts_html}</div></div>'
            f'</article>'
        )
    updated = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    page = TEMPLATE.format(
        updated=updated,
        model=html.escape(model_label),
        play_api=json.dumps(play_api or ""),
        rows="\n".join(cards),
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

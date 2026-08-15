"""采集编排：拉新歌榜 -> 入库新歌 -> 对已跟踪歌曲拍快照 -> 启发式打分.

这是 daily.py 与 CLI 各子命令共用的业务层。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from . import CHART_NEW_SONG
from .api import NcmClient
from .features import build_features
from .scoring import MODEL_VERSION, heuristic_score
from .storage import Store

log = logging.getLogger(__name__)

ML_MODEL_VERSION = "gbc-v1"

# 新歌定义：按歌曲发布时间计，发行超过该天数即停止跟踪（榜单上发布较久的歌会提前退出）
DEFAULT_NEW_SONG_WINDOW_DAYS = 45
# 单次快照最多跟踪多少首歌（控制每日请求量：约 2 req/song -> 限速 1s 约 10 分钟）
DEFAULT_MAX_TRACKED = 200


def fetch_chart_and_discover(client: NcmClient, store: Store,
                             chart_id: int = CHART_NEW_SONG) -> Dict[str, int]:
    """拉榜单 -> 记录榜单快照 -> 新面孔入库. 返回 {charted, new_songs}."""
    tracks = client.chart_tracks(chart_id)
    new_count = 0
    for t in tracks:
        store.record_chart(chart_id, t["song_id"], t["rank"])
        is_new = store.upsert_song({
            "song_id": t["song_id"],
            "name": t["name"],
            "artists": t["artists"],
            "artist_ids": t.get("artist_ids") or [],
            "album": t["album"],
            "publish_time": t.get("publish_time"),
            "duration_ms": t.get("duration_ms"),
        })
        if is_new:
            new_count += 1
    log.info("chart %s: %d tracks, %d new songs", chart_id, len(tracks), new_count)
    return {"charted": len(tracks), "new_songs": new_count}


def enrich_songs(client: NcmClient, store: Store, song_ids: List[int]) -> None:
    """批量补全歌曲详情（pop、歌手规模、发行时间）."""
    for i in range(0, len(song_ids), 100):
        batch = song_ids[i:i + 100]
        try:
            details = client.song_details(batch)
        except Exception as e:  # noqa: BLE001
            log.warning("enrich batch failed: %s", e)
            continue
        for d in details:
            store.upsert_song({
                "song_id": d["song_id"], "name": d["name"],
                "artists": d["artists"], "artist_ids": d["artist_ids"],
                "album": d["album"], "publish_time": d["publish_time"],
                "duration_ms": d["duration_ms"], "pop": d["pop"],
                "artist_album_size": d["artist_album_size"],
                "artist_music_size": d["artist_music_size"],
            })


def take_snapshots(client: NcmClient, store: Store,
                   song_ids: List[int]) -> Dict[str, int]:
    """对指定歌曲拍快照（评论总数 + 最新 pop）."""
    ok = fail = 0
    for sid in song_ids:
        total = client.comments_total(sid)
        song = store.get_song(sid)
        pop = (song or {}).get("pop")
        if total is None and pop is None:
            fail += 1
            continue
        store.add_snapshot(sid, comments_total=total, pop=pop)
        ok += 1
    log.info("snapshots: %d ok, %d failed", ok, fail)
    return {"ok": ok, "failed": fail}


def score_all(store: Store, song_ids: List[int],
              model_path: str = "model.pkl") -> List[Dict[str, Any]]:
    """对指定歌曲计算启发式分数并落库；若存在已训练模型则追加 ML 概率分."""
    ml_predict = None
    if os.path.exists(model_path):
        try:
            from .model import load_model
            clf = load_model(model_path)
            from .features import FEATURE_NAMES

            def ml_predict(feats: Dict[str, Any]) -> float:
                x = [[feats[k] for k in FEATURE_NAMES]]
                return float(clf.predict_proba(x)[0][1])
        except Exception as e:  # noqa: BLE001
            log.warning("model %s load failed, skip ML scores: %s", model_path, e)
            ml_predict = None

    results: List[Dict[str, Any]] = []
    for sid in song_ids:
        song = store.get_song(sid)
        if song is None or store.snapshots_count(sid) == 0:
            continue
        feats = build_features(store, sid)
        score, detail = heuristic_score(feats)
        store.add_score(sid, score, MODEL_VERSION, detail=detail)
        row = {
            "song_id": sid, "name": song.get("name"),
            "artists": song.get("artists"), "score": score, "detail": detail,
        }
        if ml_predict is not None:
            try:
                prob = ml_predict(feats)
                store.add_score(sid, round(prob * 100, 1), ML_MODEL_VERSION,
                                detail={"prob": round(prob, 4)})
                row["ml_score"] = round(prob * 100, 1)
            except Exception as e:  # noqa: BLE001
                log.warning("ml predict failed for %s: %s", sid, e)
        results.append(row)
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def run_daily(client: NcmClient, store: Store,
              max_tracked: int = DEFAULT_MAX_TRACKED) -> Dict[str, Any]:
    """每日例行：发现新歌 -> 补全详情 -> 快照 -> 打分."""
    stats: Dict[str, Any] = {}
    stats.update(fetch_chart_and_discover(client, store))
    # 新入库且缺 pop 的歌曲补详情
    need_enrich = [
        sid for sid in store.tracked_song_ids()
        if (store.get_song(sid) or {}).get("pop") is None
    ]
    if need_enrich:
        enrich_songs(client, store, need_enrich[:max_tracked])
    ids = store.tracked_song_ids(max_age_days=DEFAULT_NEW_SONG_WINDOW_DAYS)[:max_tracked]
    stats.update(take_snapshots(client, store, ids))
    scored = score_all(store, ids)
    stats["scored"] = len(scored)
    stats["top5"] = [
        {"name": r["name"], "artists": r["artists"], "score": r["score"]}
        for r in scored[:5]
    ]
    return stats

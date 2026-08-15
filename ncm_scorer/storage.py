"""SQLite 存储层：歌曲、每日快照、榜单记录、打分历史."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence

SCHEMA = """
CREATE TABLE IF NOT EXISTS songs (
    song_id       INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    artists       TEXT,
    artist_ids    TEXT,
    album         TEXT,
    publish_time  INTEGER,          -- ms epoch, 可能为 NULL
    duration_ms   INTEGER,
    pop           REAL,
    artist_album_size INTEGER DEFAULT 0,
    artist_music_size INTEGER DEFAULT 0,
    first_seen    INTEGER NOT NULL   -- s epoch, 首次入库时间
);

CREATE TABLE IF NOT EXISTS snapshots (
    song_id        INTEGER NOT NULL,
    ts             INTEGER NOT NULL, -- s epoch
    comments_total INTEGER,
    pop            REAL,
    PRIMARY KEY (song_id, ts)
);

CREATE TABLE IF NOT EXISTS charts (
    chart_id   INTEGER NOT NULL,
    song_id    INTEGER NOT NULL,
    rank       INTEGER,
    ts         INTEGER NOT NULL,
    PRIMARY KEY (chart_id, song_id, ts)
);

CREATE TABLE IF NOT EXISTS scores (
    song_id        INTEGER NOT NULL,
    ts             INTEGER NOT NULL,
    score          REAL NOT NULL,
    model_version  TEXT NOT NULL,
    detail         TEXT,
    PRIMARY KEY (song_id, ts, model_version)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_song_ts ON snapshots(song_id, ts);
CREATE INDEX IF NOT EXISTS idx_charts_song_ts ON charts(song_id, ts);
"""


def _now() -> int:
    return int(time.time())


class Store:
    def __init__(self, path: str = "ncm_scorer.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------- songs
    def upsert_song(self, row: Dict[str, Any]) -> bool:
        """入库/更新歌曲；返回是否为首次入库（新发现的歌曲）."""
        cur = self.conn.execute(
            "SELECT 1 FROM songs WHERE song_id=?", (row["song_id"],)
        )
        exists = cur.fetchone() is not None
        if exists:
            self.conn.execute(
                """UPDATE songs SET name=?, artists=?, artist_ids=?, album=?,
                       publish_time=COALESCE(?, publish_time), duration_ms=?,
                       pop=COALESCE(?, pop), artist_album_size=?, artist_music_size=?
                   WHERE song_id=?""",
                (row.get("name"), row.get("artists"),
                 json.dumps(row.get("artist_ids") or []), row.get("album"),
                 row.get("publish_time"), row.get("duration_ms"),
                 row.get("pop"), row.get("artist_album_size") or 0,
                 row.get("artist_music_size") or 0, row["song_id"]),
            )
            self.conn.commit()
            return False
        self.conn.execute(
            """INSERT INTO songs (song_id, name, artists, artist_ids, album,
                  publish_time, duration_ms, pop, artist_album_size,
                  artist_music_size, first_seen)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (row["song_id"], row.get("name", ""), row.get("artists"),
             json.dumps(row.get("artist_ids") or []), row.get("album"),
             row.get("publish_time"), row.get("duration_ms"),
             row.get("pop"), row.get("artist_album_size") or 0,
             row.get("artist_music_size") or 0, _now()),
        )
        self.conn.commit()
        return True

    def get_song(self, song_id: int) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute("SELECT * FROM songs WHERE song_id=?", (song_id,))
        r = cur.fetchone()
        return dict(r) if r else None

    def tracked_song_ids(self, max_age_days: float = float("inf")) -> List[int]:
        """已跟踪歌曲（可限制入库时长，避免无限膨胀）."""
        if max_age_days == float("inf"):
            cutoff = 0
        else:
            cutoff = _now() - int(max_age_days * 86400)
        cur = self.conn.execute(
            "SELECT song_id FROM songs WHERE first_seen >= ? ORDER BY song_id", (cutoff,)
        )
        return [r["song_id"] for r in cur.fetchall()]

    # --------------------------------------------------------- snapshots
    def add_snapshot(self, song_id: int, ts: Optional[int] = None,
                     comments_total: Optional[int] = None,
                     pop: Optional[float] = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO snapshots (song_id, ts, comments_total, pop) "
            "VALUES (?,?,?,?)",
            (song_id, ts or _now(), comments_total, pop),
        )
        self.conn.commit()

    def snapshots(self, song_id: int) -> List[Dict[str, Any]]:
        cur = self.conn.execute(
            "SELECT * FROM snapshots WHERE song_id=? ORDER BY ts", (song_id,)
        )
        return [dict(r) for r in cur.fetchall()]

    def last_snapshot(self, song_id: int) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute(
            "SELECT * FROM snapshots WHERE song_id=? ORDER BY ts DESC LIMIT 1",
            (song_id,),
        )
        r = cur.fetchone()
        return dict(r) if r else None

    def snapshots_count(self, song_id: int) -> int:
        cur = self.conn.execute(
            "SELECT COUNT(*) AS n FROM snapshots WHERE song_id=?", (song_id,)
        )
        return int(cur.fetchone()["n"])

    # ------------------------------------------------------------- charts
    def record_chart(self, chart_id: int, song_id: int, rank: int,
                     ts: Optional[int] = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO charts (chart_id, song_id, rank, ts) VALUES (?,?,?,?)",
            (chart_id, song_id, rank, ts or _now()),
        )
        self.conn.commit()

    def chart_hits(self, song_id: int, since_ts: Optional[int] = None) -> List[Dict[str, Any]]:
        q = "SELECT * FROM charts WHERE song_id=?"
        args: Sequence[Any] = (song_id,)
        if since_ts is not None:
            q += " AND ts >= ?"
            args = (song_id, since_ts)
        cur = self.conn.execute(q, args)
        return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------- scores
    def add_score(self, song_id: int, score: float, model_version: str,
                  detail: Optional[Dict[str, Any]] = None,
                  ts: Optional[int] = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO scores (song_id, ts, score, model_version, detail) "
            "VALUES (?,?,?,?,?)",
            (song_id, ts or _now(), float(score), model_version,
             json.dumps(detail, ensure_ascii=False) if detail else None),
        )
        self.conn.commit()

    def latest_scores(self, model_version: Optional[str] = None,
                      limit: int = 50) -> List[Dict[str, Any]]:
        q = (
            "SELECT s.song_id, s.score, s.ts, s.detail, g.name, g.artists "
            "FROM scores s JOIN (SELECT song_id, MAX(ts) AS mts FROM scores "
            "{mv} GROUP BY song_id) x ON s.song_id=x.song_id AND s.ts=x.mts "
            "JOIN songs g ON g.song_id=s.song_id ORDER BY s.score DESC LIMIT ?"
        )
        if model_version:
            mv = "WHERE model_version=?"
            args: Iterable[Any] = (model_version, model_version, limit)
        else:
            mv = ""
            args = (limit,)
        cur = self.conn.execute(q.format(mv=mv), tuple(args))
        return [dict(r) for r in cur.fetchall()]

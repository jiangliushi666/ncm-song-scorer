"""离线单元测试：不联网，覆盖特征工程与启发式打分的核心逻辑.

运行: python -m pytest tests/ -q   （或 python tests/test_offline.py）
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ncm_scorer.features import build_features   # noqa: E402
from ncm_scorer.scoring import heuristic_score   # noqa: E402
from ncm_scorer.storage import Store             # noqa: E402


def make_store() -> Store:
    return Store(os.path.join(tempfile.mkdtemp(), "t.db"))


def seed_song(store: Store, song_id: int, comments: list, pop: float = 60.0,
              publish_days_ago: float = 3.0):
    now = time.time()
    store.upsert_song({
        "song_id": song_id, "name": f"song-{song_id}", "artists": "tester",
        "artist_ids": [1], "album": "al",
        "publish_time": int((now - publish_days_ago * 86400) * 1000),
        "duration_ms": 200000, "pop": pop,
        "artist_album_size": 5, "artist_music_size": 20,
    })
    for i, c in enumerate(comments):
        store.add_snapshot(song_id, ts=int(now - (len(comments) - i) * 86400),
                           comments_total=c, pop=pop)


class TestFeatures(unittest.TestCase):
    def test_velocity_two_snapshots(self):
        store = make_store()
        seed_song(store, 1, comments=[1000, 1240])
        f = build_features(store, 1)
        self.assertAlmostEqual(f["comment_velocity_log"] > 0, True)
        self.assertEqual(f["has_velocity"], 1.0)
        self.assertGreater(f["early_density_log"], 0)

    def test_single_snapshot_no_velocity(self):
        store = make_store()
        seed_song(store, 2, comments=[500])
        f = build_features(store, 2)
        self.assertEqual(f["has_velocity"], 0.0)
        self.assertEqual(f["comment_velocity_log"], 0.0)


class TestHeuristic(unittest.TestCase):
    def test_hot_beats_cold(self):
        store = make_store()
        # 热歌：高讨论 + 高热度 + 有增速；冷歌：全低
        seed_song(store, 10, comments=[1000, 1500], pop=90.0, publish_days_ago=2)
        seed_song(store, 11, comments=[3], pop=5.0, publish_days_ago=10)
        hot, _ = heuristic_score(build_features(store, 10))
        cold, _ = heuristic_score(build_features(store, 11))
        self.assertGreater(hot, cold)
        self.assertGreaterEqual(hot, 0.0)
        self.assertLessEqual(cold, 100.0)

    def test_score_range_and_detail(self):
        store = make_store()
        seed_song(store, 12, comments=[100, 200], pop=70.0)
        score, detail = heuristic_score(build_features(store, 12))
        self.assertTrue(0.0 <= score <= 100.0)
        self.assertIn("density", detail)
        self.assertIn("weights_used", detail)
        # 单快照场景权重再分配后总和仍为 1
        w = detail["weights_used"]
        self.assertAlmostEqual(sum(w.values()), 1.0)


class TestStorage(unittest.TestCase):
    def test_upsert_and_chart_roundtrip(self):
        store = make_store()
        self.assertTrue(store.upsert_song({"song_id": 99, "name": "a"}))
        self.assertFalse(store.upsert_song({"song_id": 99, "name": "b"}))
        self.assertEqual(store.get_song(99)["name"], "b")
        store.record_chart(3779629, 99, 3)
        self.assertEqual(len(store.chart_hits(99)), 1)

    def test_window_filters_by_publish_time(self):
        store = make_store()
        now = time.time()
        # 三首歌入库时间相同（现在），发布时间不同
        store.upsert_song({  # 发布 10 天前：在 45 天窗口内
            "song_id": 21, "name": "fresh",
            "publish_time": int((now - 10 * 86400) * 1000)})
        store.upsert_song({  # 发布 70 天前：超窗，应被剔除
            "song_id": 22, "name": "old",
            "publish_time": int((now - 70 * 86400) * 1000)})
        store.upsert_song({  # 缺发布时间：回退按入库时间（刚入库 => 在窗口内）
            "song_id": 23, "name": "unknown-pt"})
        ids = store.tracked_song_ids(max_age_days=45)
        self.assertIn(21, ids)
        self.assertNotIn(22, ids)
        self.assertIn(23, ids)
        # by_publish=False 时退回旧的入库时间语义：三首都在
        ids2 = store.tracked_song_ids(max_age_days=45, by_publish=False)
        self.assertEqual(set(ids2), {21, 22, 23})


if __name__ == "__main__":
    unittest.main()

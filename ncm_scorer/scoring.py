"""启发式打分基线：零训练成本，冷启动即可给新歌排名.

分数 0-100，四个分项加权：
- 早期讨论密度 40%：评论总数/发行天数（log 压缩后 0-1 归一）
- 平台热度值 25%：官方 pop 字段，本身即 0-100
- 评论增速 20%：快照差分得出的每小时评论增量（无第二次快照时该项为 0 并回填权重）
- 歌手资历 15%：专辑数+单曲数 log 压缩

归一锚点取的是数量级参考值（见 _norm），不随数据集漂移，保证跨日可比。
"""

from __future__ import annotations

import math
from typing import Any, Dict, Tuple

MODEL_VERSION = "heuristic-v1"

WEIGHTS = {"density": 0.40, "pop": 0.25, "velocity": 0.20, "artist": 0.15}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def heuristic_score(features: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """返回 (总分 0-100, 分项明细)."""
    pop = _clamp01(float(features.get("pop") or 0.0) / 100.0)
    # log1p 锚点：1e3 条评论/天 => 密度分 0.75；1e5 条评论总量 => 总量维度饱和
    density = _clamp01(float(features.get("early_density_log") or 0.0) / math.log1p(1000) * 0.75)
    # 增速锚点：100 评论/小时 => 0.7
    velocity = _clamp01(float(features.get("comment_velocity_log") or 0.0) / math.log1p(100) * 0.7)
    # 歌手资历锚点：10 专辑 + 50 单曲 => 0.65
    artist = _clamp01(float(features.get("artist_scale") or 0.0) / math.log1p(60) * 0.65)

    has_velocity = float(features.get("has_velocity") or 0.0)
    w = dict(WEIGHTS)
    if has_velocity < 1.0:
        # 无增速数据时把 20% 权重均摊给密度与热度（新歌首日常见情形）
        w["density"] += w["velocity"] * 0.5
        w["pop"] += w["velocity"] * 0.5
        w["velocity"] = 0.0

    score = 100.0 * (
        w["density"] * density + w["pop"] * pop
        + w["velocity"] * velocity + w["artist"] * artist
    )
    detail = {
        "density": round(density * w["density"] * 100, 1),
        "pop": round(pop * w["pop"] * 100, 1),
        "velocity": round(velocity * w["velocity"] * 100, 1),
        "artist": round(artist * w["artist"] * 100, 1),
        "weights_used": w,
    }
    return round(score, 1), detail

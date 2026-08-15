"""启发式打分基线：零训练成本，冷启动即可给新歌排名.

heuristic-v2 分数 0-100，五个分项加权后再对 Live/翻唱降权：
- 早期讨论密度 36%：评论总数/发行天数（log 压缩后 0-1 归一）
- 平台热度值 22%：官方 pop 字段，本身即 0-100
- 评论增速 18%：快照差分得出的每小时评论增量（无第二次快照时该项为 0 并回填权重）
- 歌手资历 12%：专辑数+单曲数 log 压缩
- 歌手近期上榜热 12%：主歌手近 90 天其他歌曲的上榜天数（同日记录不计）

归一锚点取的是数量级参考值，不随数据集漂移，保证跨日可比。
"""

from __future__ import annotations

import math
from typing import Any, Dict, Tuple

MODEL_VERSION = "heuristic-v2"

WEIGHTS = {
    "density": 0.36,
    "pop": 0.22,
    "velocity": 0.18,
    "artist": 0.12,
    "artist_heat": 0.12,
}

# Live/现场/翻唱不是原创新歌，乘降权系数后再截断到 0-100
LIVE_PENALTY = 0.78


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def heuristic_score(features: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """返回 (总分 0-100, 分项明细)."""
    pop = _clamp01(float(features.get("pop") or 0.0) / 100.0)
    # log1p 锚点：1e3 条评论/天 => 密度分 0.75
    density = _clamp01(float(features.get("early_density_log") or 0.0) / math.log1p(1000) * 0.75)
    # 增速锚点：100 评论/小时 => 0.7
    velocity = _clamp01(float(features.get("comment_velocity_log") or 0.0) / math.log1p(100) * 0.7)
    # 歌手资历锚点：10 专辑 + 50 单曲 => 0.65
    artist = _clamp01(float(features.get("artist_scale") or 0.0) / math.log1p(60) * 0.65)
    # 近 90 天上榜 10 天 => 0.7
    artist_heat = _clamp01(
        float(features.get("artist_chart_days_log") or 0.0) / math.log1p(10) * 0.7
    )

    has_velocity = float(features.get("has_velocity") or 0.0)
    w = dict(WEIGHTS)
    if has_velocity < 1.0:
        # 无增速数据时把权重均摊给密度与热度（新歌首日常见情形）
        w["density"] += w["velocity"] * 0.5
        w["pop"] += w["velocity"] * 0.5
        w["velocity"] = 0.0

    raw = 100.0 * (
        w["density"] * density
        + w["pop"] * pop
        + w["velocity"] * velocity
        + w["artist"] * artist
        + w["artist_heat"] * artist_heat
    )
    is_live = float(features.get("is_live") or 0.0) >= 1.0
    penalty = LIVE_PENALTY if is_live else 1.0
    score = max(0.0, min(100.0, raw * penalty))
    detail = {
        "density": round(density * w["density"] * 100, 1),
        "pop": round(pop * w["pop"] * 100, 1),
        "velocity": round(velocity * w["velocity"] * 100, 1),
        "artist": round(artist * w["artist"] * 100, 1),
        "artist_heat": round(artist_heat * w["artist_heat"] * 100, 1),
        "is_live": is_live,
        "live_penalty": penalty,
        "weights_used": w,
    }
    return round(score, 1), detail

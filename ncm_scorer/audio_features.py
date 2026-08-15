"""可选音频内容特征（librosa）.

网易云试听外链对外部访问不稳定（实测多数歌曲 302 -> 404），因此本模块定位为：
对用户提供的本地音频文件（自购/合法获取）提取内容特征，供打分层融合。

安装可选依赖：pip install librosa numpy
"""

from __future__ import annotations

import logging
from typing import Any, Dict

log = logging.getLogger(__name__)

AUDIO_FEATURE_NAMES = [
    "tempo",                # BPM
    "energy_rms_log",       # log1p(RMS 能量)
    "danceability_proxy",   # 节拍稳定度代理：onset 强度方差的负归一
    "brightness_proxy",     # 频谱质心归一（亮度）
]


def extract(audio_path: str) -> Dict[str, float]:
    """从本地音频文件提取内容特征，librosa 未安装时抛出友好错误."""
    try:
        import librosa  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("音频特征需要可选依赖：pip install librosa numpy") from e

    y, sr = librosa.load(audio_path, sr=22050, mono=True, duration=120.0)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(np.atleast_1d(tempo)[0])
    rms = float(librosa.feature.rms(y=y).mean())
    centroid = float(librosa.feature.spectral_centroid(y=y, sr=sr).mean())
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    # 节拍越稳定（onset 方差小）danceability 越高
    onset_cv = float(np.std(onset_env) / (np.mean(onset_env) + 1e-9))
    dance = max(0.0, 1.0 - onset_cv)

    import math
    return {
        "tempo": tempo,
        "energy_rms_log": math.log1p(rms),
        "danceability_proxy": round(dance, 4),
        "brightness_proxy": round(centroid / (sr / 2), 4),
    }

"""ncm-scorer: 网易云音乐新歌自动评分系统（开源）.

数据层直连 music.163.com 明文 API（均已实测可用，见 docs/API_ENDPOINTS.md），
存储用 SQLite，打分层包含零训练成本的启发式基线与可选的机器学习模型。
"""

__version__ = "0.1.0"

# 网易云音乐直连榜单 ID（实测 2026-08）
CHART_NEW_SONG = 3779629   # 新歌榜（每日 100 首，直连可用，核心标签源）
CHART_HOT_SONG = 3778678   # 热歌榜（直连路径暂无数据，保留配置位）
CHART_SOARING = 19723756   # 飙升榜（同上）

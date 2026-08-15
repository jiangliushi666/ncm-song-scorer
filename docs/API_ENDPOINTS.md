# 网易云音乐明文 API 端点实测记录

实测时间：2026-08-14（Windows + 直连，无 Cookie / 无 weapi 加密）

公共请求头：

```
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ...
Referer: https://music.163.com
```

## ✅ 可用端点

### 1. 新歌榜（核心数据源 + 标签源）

```
GET https://music.163.com/api/playlist/detail?id=3779629
```

- 返回 `result.playlist.tracks[]`，含 100 首歌：id / name / artists / album(name, publishTime) / duration
- 顺带每首歌的榜内位置 = 数组下标 + 1
- 实测返回示例：`{"code":200,"name":"新歌榜","n_tracks":100}`

### 2. 歌曲详情（批量）

```
GET https://music.163.com/api/song/detail/?id={first_id}&ids=[{id1},{id2},...]
```

- 关键字段：`popularity`（平台热度 0-100）、`album.publishTime`（发行时间 ms）、
  `artists[0].albumSize / musicSize`（歌手专辑数/单曲数，资历代理）
- 实测：海阔天空 → `{"pop":100.0,"publishTime":747504000000}`

### 3. 评论总数

```
GET https://music.163.com/api/v1/resource/comments/R_SO_4_{song_id}?limit=1&offset=0
```

- 关键字段：`total`（评论总数）
- 实测：海阔天空 → `{"total":70442,"code":200}`

### 4. 歌手热门歌曲（邻域负样本）

```
GET https://music.163.com/api/artist/top/song?id={artist_id}
```

- 实测可用（返回该歌手热门曲目）
- daily 流程用来发现「上榜歌手的其他近作、但未进新歌榜」的歌，作为 ML 负样本
- 每日上限约 12 位歌手 / 20 首新入库，避免放大请求量

## ❌ 实测不可用（避坑记录）

| 端点 | 结果 | 结论 |
|---|---|---|
| `GET /api/v3/discovery/songs`（新歌速递） | 404 | 新歌速递需 weapi，放弃；用新歌榜替代 |
| `GET /api/discovery/songs?areaId=7` | 404 | 同上 |
| `GET /api/playlist/detail?id=3778678`（热歌榜） | 200 但 tracks 空 | 直连无数据，榜单配置位保留 |
| `GET /api/playlist/detail?id=19723756`（飙升榜） | 200 但 tracks 空 | 同上 |
| `GET /api/artist/details?id=` | 空 data | 弃用，歌手规模改从歌曲详情的 artists 字段取 |
| `GET /api/artist/get?id=` | 400 参数错误 | 弃用 |
| `https://music.163.com/song/media/outer/url?id={id}.mp3` | 302 → 404 | 试听外链不稳定，音频特征改为本地文件模式 |

## 变更监控建议

明文接口非官方契约。若 `chart_tracks` 突然返回空列表，优先排查：

1. 端点路径是否变更（抓包网页版对照）；
2. 是否开始要求 Cookie（尝试补 `Cookie: os=pc` 等通用头）；
3. 接口是否迁移到 weapi（届时引入 [NeteaseCloudMusicApiEnhanced](https://github.com/NeteaseCloudMusicApiEnhanced) 本地代理）。

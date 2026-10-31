# openrowan.com（OpenRowan 官网）

OpenRowan 工作室的官网：每个 App 一页（价格、截图、隐私政策、支持），英文首页加中文首页 `/zh/`。

> **推送 `main` 就是上线**（Cloudflare Pages 自动构建）。改之前先本地预览，公开内容要先让负责人确认。

## 它怎么运转

- **Hugo**（0.154+）静态站，主题 `themes/studio`（`themes/rowan` 是没用的旧主题）。
- **App 数据分两层**：
  - `data/apps/<slug>.yaml` 是人写的（名称、分类、标语、状态 `coming_soon / live / hidden`、中文标语 `tagline_zh`）；
  - `data/store/<slug>.json` 和 `static/images/apps/` 是**自动生成**的：GitHub Actions 每天跑 `scripts/sync_apps.py`，查公开的 iTunes API 拿价格、链接、图标、截图，有变化才提交。**不要手改这两处。**
- **双语**：`i18n/en.yaml`、`i18n/zh.yaml` 放界面文案，`content/_index.zh.md` 是中文首页；App 名字不翻译，App 详情页只有英文。
- **配色和 logo**：来自 openrowan-platform 的 `brand/`（`tokens.css`、`dist/`）；不要在这里另起一套颜色。

## 新增一个 App

```bash
python scripts/add_app.py --slug henLog --name HenLog --category keepers --tagline 'Flock and egg tracker' \
  --bundle-id com.raylenzed.henlog --asc-app-id 6789515325      # 写 data/apps/<slug>.yaml（coming_soon）和 content/apps/<slug>/_index.md
# 再给新 App 补一句中文标语：在 data/apps/<slug>.yaml 里加 tagline_zh
```

App 上架后，每日同步会自动补上商店链接、价格、图标和截图，状态自动变 live。

## 本地预览

```bash
hugo server        # http://localhost:1313/（中文页在 /zh/）
hugo --minify      # 构建到 public/
```

仓库里偶尔会出现 `xxx 2.yaml` 这样的文件，那是 iCloud 同步冲突产生的重复文件，**不要提交**；新仓库请放在 `~/Github`，不要放 `~/Documents`。

## 自动任务（`.github/workflows/`）

| 文件 | 作用 |
|---|---|
| `sync-apps.yml` | 每天 02:17 UTC 同步 App Store 数据并提交 |
| `uptime.yml` | 每 10 分钟从外部检查官网、Console、API；失败时 GitHub 给仓库主人发邮件 |

## 和别的项目的关系

- 数据来源是 App Store（不是 Console）；Console 的 worker 只读本仓库的 App 图标。
- 全景见 openrowan-platform 的 `docs/ECOSYSTEM.md`。

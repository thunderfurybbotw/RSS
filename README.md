# ForeverChanges 更新档说明 → RSS

每 6 小时抓取一次 https://foreverchanges.pro/zh-tw/patch-notes ，生成 `feed.xml` 并发布到 GitHub Pages。

## 设置（约 5 分钟）

1. 在 GitHub 新建一个仓库（例如 `foreverchanges-rss`），可以是 Public。
   私有仓库使用 Pages 需要付费账户。
2. 把本文件夹里的内容原样上传到仓库根目录，保留 `.github/workflows/rss.yml` 这个路径。
3. 进入仓库的 **Settings → Pages**，把 **Source** 设为 **GitHub Actions**。
4. 进入 **Actions** 页，选择 “Build RSS” → **Run workflow**，手动跑第一次。
5. 运行成功后，订阅地址是：
   `https://<你的GitHub用户名>.github.io/<仓库名>/feed.xml`
   把它加到 Inoreader、Reeder、NetNewsWire 等阅读器里即可。

## 常用修改

- **改成简体版**：把 `rss.yml` 里的 `--lang zh-tw` 改成 `--lang zh-cn`。
- **改抓取频率**：修改 `cron` 行。GitHub 的定时任务可能会延迟几分钟到几十分钟，这是正常现象。
- **本地测试**：
  ```
  pip install requests beautifulsoup4
  python fetch_feed.py
  ```

## 注意

- 如果页面改版、解析不到条目，脚本会报错退出。Actions 会显示失败，但已发布的旧 feed 不会被空内容覆盖。
- 每条 RSS 的 guid 是版本号，所以同一版本即使正文后来被作者补充，阅读器一般也不会重复推送。
- 网站由作者一个人维护，请不要把频率调得太高。

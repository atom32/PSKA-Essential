# PSKA WebUI Demo Package

这是给演示使用的入口页。优先使用真实录屏旁白成片；需要更改字幕、旁白或镜头节奏时，再进入下方的可替换素材和构建脚本。

## 直接展示

- 主视频：`dist/pska_webui_browser_recording_narrated.mp4`
- 外置字幕：`dist/pska_webui_browser_recording_narrated.zh.srt`
- 本地报告页：`report.html`
- 功能证据矩阵：`FEATURE_EVIDENCE_MATRIX.zh.md`
- 剪映导入说明：`JIANYING_IMPORT.zh.md`

主视频来自真实 Playwright Chromium 操作录屏，并叠加中文旁白音轨。它展示了 Home/Jarvis、Agentic Context Brief、Ask、Sourced Brief、Loop Trace、Memory Card、Activity audit、Sources 和 no-embedding search。

## 备用素材

- 真实浏览器录屏无旁白版：`dist/pska_webui_browser_recording.mp4`
- 真实浏览器录屏字幕：`dist/pska_webui_browser_recording.zh.srt`
- 截图 replay 讲解版：`dist/pska_webui_browser_demo.mp4`
- 截图 replay 字幕：`dist/pska_webui_browser_demo.zh.srt`
- 真实录屏分镜：`dist/playwright_storyboard.zh.md`
- 旁白成片分镜：`dist/playwright_narrated_storyboard.zh.md`
- 旁白稿：`dist/playwright_narrated_voiceover.zh.md`
- Brief 证据帧：`dist/posters/01_context_brief.png`
- Sourced Brief 证据帧：`dist/posters/02_sourced_brief.png`
- no-embedding search 证据帧：`dist/posters/03_source_search.png`

## 重新生成

生成截图 replay：

```bash
python3 scripts/build_browser_demo_video.py
```

录制真实浏览器操作：

```bash
NODE_PATH=/tmp/pska-playwright-recorder/node_modules \
  node scripts/record_browser_demo_video.cjs
```

生成真实录屏旁白成片：

```bash
python3 scripts/build_recording_narrated_cut.py
```

验证整个演示包：

```bash
python3 scripts/verify_browser_demo_pack.py
```

生成可分发 zip：

```bash
python3 scripts/package_browser_demo_pack.py
```

默认输出：

- `dist/pska_webui_demo_package.zip`
- `dist/pska_webui_demo_package_manifest.json`

解压后打开 `pska_webui_demo/report.html` 即可播放主视频并查看证据矩阵。

## 验收标准

- 主视频是 `1280x720` H.264，并包含 AAC 音频轨。
- 真实录屏无旁白版保留为 `1280x720` H.264 视频轨。
- 三份字幕均有 10 个有序镜头块。
- Playwright manifest 记录 dataset、document、source root 和 memory id。
- 剪映导入说明中的本地素材路径都能解析到实际文件。
- 分发 zip 不包含 raw WebM、Playwright build 临时目录、`.DS_Store` 或 `__pycache__`。

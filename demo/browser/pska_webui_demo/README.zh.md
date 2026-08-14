# PSKA WebUI 浏览器操作演示

这个目录保存 PSKA WebUI 操作演示素材。它和 `demo/video/pska_m31_demo` 的区别是：这里展示真实 Product API fake-mode 功能闭环，而不是只讲系统概念。

演示包入口见 `DEMO_PACKAGE.zh.md`，本地报告页见 `report.html`，剪映导入说明见 `JIANYING_IMPORT.zh.md`。

当前有两类视频产物：

- `pska_webui_browser_demo.mp4`：真实浏览器截图 replay，带指针、字幕和较慢节奏，适合讲解。
- `pska_webui_browser_recording.mp4`：Playwright 录出的真实 Chromium 操作视频，页面点击、输入、滚动和结果渲染都来自浏览器运行过程。
- `pska_webui_browser_recording_narrated.mp4`：基于真实 Chromium 录屏生成的慢速旁白成片，适合直接展示或导入剪映精剪。

覆盖功能：

- Home / Jarvis briefing。
- Agentic Context Brief。
- 从 Brief next action 进入 Ask。
- Sourced Brief、Source Manifest、Memory Attribution。
- Agentic Loop Trace。
- Memory Card 页面。
- Activity audit 页面。
- Sources 本地文件夹注册状态。
- 无 embedding search 命中文件。

## 生成视频

```bash
cd /Users/xudawei/PSKA-Essential
python3 scripts/build_browser_demo_video.py
```

默认输出：

```text
demo/browser/pska_webui_demo/dist/pska_webui_browser_demo.mp4
demo/browser/pska_webui_demo/dist/pska_webui_browser_demo.zh.srt
demo/browser/pska_webui_demo/dist/storyboard.zh.md
demo/browser/pska_webui_demo/dist/voiceover.zh.md
```

如需无旁白版本：

```bash
python3 scripts/build_browser_demo_video.py --voice none
```

## 截图 Replay 说明

这版是基于真实浏览器操作截图的 replay demo，不是系统级连续屏幕录制。它的优点是稳定、可复现、能在 CI 或本地快速重建；如果后续要做剪映成片，可以把这版作为底片，再替换成 Playwright video 或 macOS 录屏素材。

## 生成真实浏览器录制

如需 Playwright 录出的真实浏览器视频轨道，先准备临时依赖：

```bash
mkdir -p /tmp/pska-playwright-recorder
cd /tmp/pska-playwright-recorder
npm init -y
npm install playwright@1.62.1
npx playwright install chromium
```

然后回到项目根目录录制：

```bash
cd /Users/xudawei/PSKA-Essential
NODE_PATH=/tmp/pska-playwright-recorder/node_modules \
  node scripts/record_browser_demo_video.cjs
```

默认输出：

```text
demo/browser/pska_webui_demo/dist/pska_webui_browser_recording.mp4
demo/browser/pska_webui_demo/dist/pska_webui_browser_recording.zh.srt
demo/browser/pska_webui_demo/dist/playwright_storyboard.zh.md
demo/browser/pska_webui_demo/dist/playwright_recording_manifest.json
```

这个录制脚本会启动 fake Product API、种入演示知识库/资料源/记忆，然后用真实 Chromium 页面完成点击和输入流程。

## 生成真实录屏旁白成片

```bash
cd /Users/xudawei/PSKA-Essential
python3 scripts/build_recording_narrated_cut.py
```

默认输出：

```text
demo/browser/pska_webui_demo/dist/pska_webui_browser_recording_narrated.mp4
demo/browser/pska_webui_demo/dist/pska_webui_browser_recording_narrated.zh.srt
demo/browser/pska_webui_demo/dist/playwright_narrated_storyboard.zh.md
demo/browser/pska_webui_demo/dist/playwright_narrated_voiceover.zh.md
demo/browser/pska_webui_demo/dist/playwright_narrated_manifest.json
```

## 验证演示包

```bash
cd /Users/xudawei/PSKA-Essential
python3 scripts/verify_browser_demo_pack.py
```

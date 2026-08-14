# PSKA WebUI 浏览器操作演示

这个目录保存 PSKA WebUI 操作演示素材。它和 `demo/video/pska_m31_demo` 的区别是：这里使用真实浏览器页面截图，展示一次完整的 Product API fake-mode 功能闭环。

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

## 说明

这版是基于真实浏览器操作截图的 replay demo，不是系统级连续屏幕录制。它的优点是稳定、可复现、能在 CI 或本地快速重建；如果后续要做剪映成片，可以把这版作为底片，再替换成 Playwright video 或 macOS 录屏素材。

# PSKA Product API 诊断页素材剪映导入包

这个包用于把 PSKA Product API 本地诊断页浏览器素材导入剪映专业版继续精剪。当前不依赖直接控制剪映，所有素材都在本目录下可直接导入。

注意：这不是 Hermes WebUI extension 的产品演示。对外功能演示应重新录制 Hermes WebUI 内的 `pska-mini` extension、Hermes chat、PSKA MCP/tool card 和 sidecar proxy 路径。

## 推荐主素材

- 主视频：`dist/pska_webui_browser_recording_narrated.mp4`
- 字幕：`dist/pska_webui_browser_recording_narrated.zh.srt`
- 分镜：`dist/playwright_narrated_storyboard.zh.md`
- 旁白稿：`dist/playwright_narrated_voiceover.zh.md`
- 构建记录：`dist/playwright_narrated_manifest.json`

这版是基于真实 Playwright Chromium 录屏生成的慢速旁白成片，包含视频轨和 AAC 音频轨，适合直接对外展示。

## 可替换素材

- 真实录屏无旁白版：`dist/pska_webui_browser_recording.mp4`
- 真实录屏无旁白字幕：`dist/pska_webui_browser_recording.zh.srt`
- 截图 replay 讲解版：`dist/pska_webui_browser_demo.mp4`
- 截图 replay 字幕：`dist/pska_webui_browser_demo.zh.srt`
- 真实录屏 raw WebM：`dist/pska_webui_browser_recording_raw.webm`

## 推荐时间线

| 时间 | 镜头 | 展示点 |
| --- | --- | --- |
| 00:00:05.777 - 00:00:15.713 | 打开 PSKA 诊断页 | Product API、Home、Jarvis、资料源、记忆信号 |
| 00:00:15.713 - 00:00:29.166 | 生成 Agentic Context Brief | KB evidence、source recall、Memory Card、trace、next actions |
| 00:00:29.166 - 00:00:36.034 | 从 Brief 进入 Ask | ready knowledge scope 自动带入 |
| 00:00:36.034 - 00:00:49.480 | 填写问题并运行 Ask | 真实输入问题并运行提问 |
| 00:00:49.480 - 00:01:03.417 | 查看带来源 Brief | run id、source count、inspected source count、used memory count |
| 00:01:03.417 - 00:01:16.248 | 查看 Agentic Loop Trace | scope、governance、readiness、retrieval、memory、source inspection |
| 00:01:16.248 - 00:01:32.682 | 打开 Memory Card 页面 | 最近使用记忆、为什么用到、时间线、查看入口 |
| 00:01:32.682 - 00:01:46.611 | 打开 Activity 审计记录 | agentic_loop.complete、run、ready、context 标签 |
| 00:01:46.611 - 00:01:59.440 | 打开 Sources 本地资料源 | read only、scanned、objects 1、扫描/抽取/审计入口 |
| 00:01:59.440 - 00:02:15.266 | 运行无 embedding 搜索 | browser demo 命中 pska-demo-note.md、行号和摘要 |

## 剪映建议

- 主轨导入 `pska_webui_browser_recording_narrated.mp4`。
- 字幕导入同名 `.zh.srt`，保留外置字幕，便于后续改字。
- 如需更紧凑，把每个镜头末尾的停顿缩短，但保留 Ask 结果、Loop、Memory、Sources search 四个证据镜头。
- 如需更正式，开头可加 3 秒标题页：`PSKA Product API 诊断素材：Agentic Context Brief / Memory / Trace / no-embedding Source Recall`。
- 如需替换 AI 旁白，用 `dist/playwright_narrated_voiceover.zh.md` 重新录音，再在剪映中替换音轨。

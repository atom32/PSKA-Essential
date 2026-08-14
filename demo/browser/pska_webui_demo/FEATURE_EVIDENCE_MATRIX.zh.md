# PSKA WebUI 功能证据矩阵

这份矩阵用于回答“视频到底展示了哪些真实功能点”。主证据视频是 `dist/pska_webui_browser_recording_narrated.mp4`，对应字幕是 `dist/pska_webui_browser_recording_narrated.zh.srt`。

| 功能点 | 视频时间 | 可见证据 | 关联产物 |
| --- | --- | --- | --- |
| Home / Jarvis briefing | 00:00:05.777 - 00:00:15.713 | Home 页面显示 Product API 已连接、知识库计数、Jarvis briefing、资料源和记忆信号。 | `dist/playwright_narrated_manifest.json` |
| Agentic Context Brief | 00:00:15.713 - 00:00:29.166 | Brief 区域显示 evidence 1、sources 1、memory 1、trace 4，并有 Recall、Memory、Trace、Next 四栏。 | `dist/posters/01_context_brief.png` |
| Brief -> Ask 的入口联动 | 00:00:29.166 - 00:00:36.034 | 从 Brief 的 next action 进入 Ask 页面，知识库 scope 自动带入。 | `dist/playwright_narrated_storyboard.zh.md` |
| 真实问题输入与运行 | 00:00:36.034 - 00:00:49.480 | Ask 页面显示真实输入的问题，并点击运行提问。 | `dist/pska_webui_browser_recording.mp4` |
| Sourced Brief | 00:00:49.480 - 00:01:03.417 | 结果包含 run id、source count、inspected source count、used memory count。 | `dist/posters/02_sourced_brief.png` |
| Source Manifest / Memory Attribution | 00:00:49.480 - 00:01:03.417 | 结果 brief 下方包含 Source Manifest 与 Memory Attribution 区域。 | `dist/pska_webui_browser_recording_narrated.mp4` |
| Agentic Loop Trace | 00:01:03.417 - 00:01:16.248 | Loop 展示 scope.check、governance.policy、kb.readiness、retrieval.plan、memory.search、source.inspect。 | `dist/playwright_narrated_storyboard.zh.md` |
| Memory Card 治理入口 | 00:01:16.248 - 00:01:32.682 | Memory 页面展示最近使用的记忆卡片，以及为什么用到、时间线、查看等入口。 | `dist/playwright_narrated_manifest.json` |
| Activity audit | 00:01:32.682 - 00:01:46.611 | Activity 页面展示 agentic_loop.complete，并保留 run、ready、context 等审计标签。 | `dist/pska_webui_browser_recording_narrated.zh.srt` |
| Sources 本地资料源 | 00:01:46.611 - 00:01:59.440 | Sources 页面展示 read only、scanned、objects 1 的本地文件夹。 | `dist/playwright_recording_manifest.json` |
| 无 embedding search | 00:01:59.440 - 00:02:15.266 | 搜索 browser demo，命中本地 Markdown 文件 pska-demo-note.md，显示行号和摘要。 | `dist/posters/03_source_search.png` |

## 验证命令

```bash
python3 scripts/verify_browser_demo_pack.py
```

验证脚本会检查视频流、音轨、字幕、manifest seed、poster 和本地引用是否完整。

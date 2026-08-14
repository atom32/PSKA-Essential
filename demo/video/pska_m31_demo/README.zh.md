# PSKA M31 Demo Video Pack

这个目录保存 PSKA 功能演示视频的源分镜。

当前定位：

- 展示 PSKA 作为 `source-first / memory-governed / agent-operated` 的外部认知系统。
- 覆盖 Home/Jarvis、Agentic Context Brief、Alpha Guide、First-run checklist、Source Recall、Agentic Ask、Memory Governance、Trace、Eidolia 和安全边界。
- 明确说明当前是 technical alpha / dogfood 阶段，不是普通 To C 正式产品。

## 生成视频

```bash
cd /Users/xudawei/PSKA-Essential
python3 scripts/build_demo_video.py
```

默认会使用 macOS `say` 的 `Tingting` 中文语音生成旁白。输出在：

```text
demo/video/pska_m31_demo/dist/pska_m31_demo.mp4
demo/video/pska_m31_demo/dist/pska_m31_demo.zh.srt
demo/video/pska_m31_demo/dist/storyboard.zh.md
demo/video/pska_m31_demo/dist/voiceover.zh.md
```

如果只想生成无旁白视频：

```bash
python3 scripts/build_demo_video.py --voice none
```

如果想换中文语音：

```bash
python3 scripts/build_demo_video.py --voice "Flo (中文（中国大陆）)"
```

## 导入剪映

本机构建流程不依赖剪映。需要进剪映时，导入：

```text
pska_m31_demo.mp4
pska_m31_demo.zh.srt
```

剪映里可以再替换某些 slide 片段为真实 WebUI/Eidolia 录屏，并保留同一份字幕时间轴。

## 后续可替换素材

这一版是可复现的 slide demo。后续可以把以下段落替换成真实录屏：

- Home / Jarvis / Agentic Context Brief / Alpha Trial Guide。
- First-run checklist 的状态和备注保存。
- Sources panel 的 folder / Obsidian scan、search、neighbors、audit。
- Ask 页面的一次 sourced Q&A。
- Memory Review Queue / Memory Card refresh。
- Trace query 和 Eidolia thought/artifact bridge。

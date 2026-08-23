# 客户实操演示视频录制手册

这条视频面向客户，不讲内部实现。客户只需要看懂三件事：

- 它在原来的对话工作台里使用，不需要另开一个复杂系统。
- 它只读取用户允许的资料，把资料、记忆和操作记录整理给助手使用。
- 它能落到真实工作：查资料、问问题、管理记忆、跟进任务，并把材料送进创作画布。

## 推荐成片结构

建议做成一条五到七分钟的视频，主线如下：

| 时间 | 画面 | 旁白重点 |
| --- | --- | --- |
| 0:00-0:30 | 打开对话工作台，看到知识助手入口 | 这是用户每天聊天和工作的主入口 |
| 0:30-1:20 | 选择本轮资料范围，刷新连接状态 | 系统只看本轮允许的资料，不扫全盘 |
| 1:20-2:10 | 点开始前总览、回答前整理、资料找回 | 回答前先把资料、记忆和下一步动作整理好 |
| 2:10-3:00 | 在对话框里发问并等待回答 | 用户仍然是在正常聊天，不跳到独立问答页 |
| 3:00-3:50 | 打开记忆页、待确认内容、回答记录 | 长期记忆要有来源，并由用户确认 |
| 3:50-4:30 | 同步审核和整理任务 | 需要后续处理的事情会进入任务列表 |
| 4:30-5:40 | 财报案例或网文案例 | 证明它能用于真实资料分析和创作 |
| 5:40-7:00 | 打开创作画布，展示想法和产物节点 | 创作画布接住资料和草稿，知识助手继续管来源和记忆 |

如果只录一条，优先录网文作者案例，因为它同时展示了资料找回、记忆候选、正常对话和创作画布。  
如果要面向企业客户，可以再补一条财报案例。

## 现有可用素材

本机已经有五个通过检查的视频包，并可生成一个硬字幕版本；默认视频都没有音轨，适合导入剪映后配音：

- `dist/hermes_pska_customer_walkthrough_demo.mp4`：客户版合成主片，约五分二十五秒。
- `dist/hermes_pska_customer_walkthrough_demo_subtitled.mp4`：硬字幕版主片，适合直接发给客户预览。
- `dist/hermes_pska_customer_walkthrough_demo_subtitled_voiceover.mp4`：带机器旁白的有声预览版，适合内部快速过片或给客户先看。
- `dist/hermes_pska_extension_demo_long.mp4`：核心长版，约三分二十一秒。
- `dist/hermes_pska_finance_case_demo.mp4`：财报调研案例，约两分三秒。
- `dist/hermes_pska_webnovel_case_demo.mp4`：网文续写和创作画布案例，约两分十四秒。
- 每个视频旁边都有同名 `.zh.srt` 字幕文件。
- 客户版主片旁边还有同名 `_voiceover.zh.md` 旁白稿，适合人工讲解；同名 `_voiceover_tts.zh.txt` 是纯旁白文本，适合导入剪映生成中文配音。

这些字幕已经按“客户能听懂”的口径写好，不使用英文术语。

## 最省事的交付方式

如果只是要给客户看，不需要重新录制。直接使用已经合成好的客户版主片：

```text
demo/browser/hermes_pska_extension_demo/dist/hermes_pska_customer_walkthrough_demo.mp4
```

推荐按这个顺序处理：

1. 先看 `hermes_pska_customer_walkthrough_demo_preview_sheet.jpg`，确认画面顺序。
2. 直接播放时，使用 `hermes_pska_customer_walkthrough_demo_subtitled.mp4`。
   如果已经生成有声预览，也可以直接播放 `hermes_pska_customer_walkthrough_demo_subtitled_voiceover.mp4`。
3. 需要二次剪辑时，把 `hermes_pska_customer_walkthrough_demo.mp4` 导入剪映。
4. 导入 `hermes_pska_customer_walkthrough_demo.zh.srt` 作为字幕。
5. 用 `hermes_pska_customer_walkthrough_demo_voiceover_tts.zh.txt` 生成中文配音；人工讲解时看 `hermes_pska_customer_walkthrough_demo_voiceover.zh.md`。
6. 导出前检查最后一段是否保留创作画布、想法节点、产物节点和续写草稿。

对外转交时，优先发送：

```text
demo/browser/hermes_pska_extension_demo/dist/hermes_pska_customer_walkthrough_demo_delivery_pack.zip
demo/browser/hermes_pska_extension_demo/dist/hermes_pska_customer_walkthrough_demo_delivery_pack.zip.sha256
```

## 重新录制前检查

先确认三个入口在线：

```bash
curl -fsS http://127.0.0.1:8765/api/health
curl -fsS http://127.0.0.1:8787/api/auth/status
curl -fsS http://127.0.0.1:8797/api/agent/health
```

如果扩展刚改过，先同步到对话工作台：

```bash
./integrations/hermes-webui-extension/sync-to-hermes.sh
```

## 重新录制命令

优先使用一键重录和打包：

```bash
HERMES_WEBUI_PASSWORD=011235 make demo-browser-customer-record-package
```

这条命令会依次录制核心长版、财报案例、网文续写和创作画布案例，然后合成客户版主片、生成字幕、旁白稿和纯旁白文本，打包交付文件，并做完整检查。

如果只想先看会执行什么，不实际录制：

```bash
make demo-browser-customer-record-package DEMO_RECORD_ARGS="--dry-run"
```

如果要在录制前只检查环境，不开始录屏：

```bash
HERMES_WEBUI_PASSWORD=011235 make demo-browser-customer-record-package DEMO_RECORD_ARGS="--preflight-only"
```

检查会提前确认 Node、ffmpeg、录制依赖、对话工作台、知识助手服务和创作画布服务是否可用。

如果只想在本机加一个带机器旁白的客户预览版，不重新录浏览器画面：

```bash
make demo-browser-customer-audio-package
```

这会使用字幕文本生成中文机器旁白，并额外产出
`hermes_pska_customer_walkthrough_demo_subtitled_voiceover.mp4`。无音轨主片仍然是剪辑源文件。

下面的三条命令用于单独重录某一段，或者排查某个 case 的问题。

核心长版：

```bash
NODE_PATH=/tmp/pska-playwright-recorder/node_modules \
HERMES_WEBUI_PASSWORD=011235 \
node scripts/record_hermes_pska_extension_demo.cjs \
  --detailed \
  --dwell-scale 4 \
  --wait-for-llm-ms 75000 \
  --output-basename hermes_pska_extension_demo_long
```

财报调研案例：

```bash
NODE_PATH=/tmp/pska-playwright-recorder/node_modules \
HERMES_WEBUI_PASSWORD=011235 \
node scripts/record_hermes_pska_extension_demo.cjs \
  --case finance_report_research \
  --detailed \
  --dwell-scale 2.5 \
  --wait-for-llm-ms 30000
```

网文续写和创作画布案例：

```bash
NODE_PATH=/tmp/pska-playwright-recorder/node_modules \
HERMES_WEBUI_PASSWORD=011235 \
node scripts/record_hermes_pska_extension_demo.cjs \
  --case webnovel_author \
  --detailed \
  --dwell-scale 2.5 \
  --wait-for-llm-ms 30000
```

把核心、财报和网文三段素材合成客户版主片，并生成可交付压缩包：

```bash
make demo-browser-customer-package
```

录完后检查全部视频：

```bash
python3 scripts/verify_hermes_extension_demo_pack.py --all-videos --require-video --require-delivery-pack
```

## 剪映处理建议

1. 导入 `mp4` 视频。
2. 导入同名 `.zh.srt` 字幕。
3. 用同名 `_voiceover_tts.zh.txt` 纯旁白文本生成中文配音，语速选偏慢。
4. 保留原始操作画面，不要改成幻灯片。
5. 如果画面等待时间太长，只裁短等待，不删掉“发问到回答”的过程。

推荐使用顺序：

1. 直接使用 `hermes_pska_customer_walkthrough_demo.mp4` 作为主片。
2. 导入 `hermes_pska_customer_walkthrough_demo.zh.srt` 作为字幕。
3. 用 `hermes_pska_customer_walkthrough_demo_voiceover_tts.zh.txt` 作为配音文本。
4. 解压后可先看 `hermes_pska_customer_walkthrough_demo_preview_sheet.jpg`，确认关键画面顺序。
5. 如果要发给他人处理，使用 `hermes_pska_customer_walkthrough_demo_delivery_pack.zip`，并同时带上旁边的 `.zip.sha256` 校验文件和 `_delivery_handoff.zh.md` 外部说明。
6. 如果要加长讲解，再补财报案例或网文案例的完整视频。

## 实操讲解顺序

录制或现场讲解时，不要先讲架构。按客户实际使用顺序讲：

| 顺序 | 画面动作 | 讲给客户听的话 |
| --- | --- | --- |
| 1 | 打开对话工作台 | 这是用户每天提问和工作的地方，不需要另开系统。 |
| 2 | 点开知识助手入口 | 这个入口负责选择资料、查看状态、准备回答。 |
| 3 | 选择本轮资料范围 | 这次只看用户允许的资料，不扫全盘。 |
| 4 | 点开始前总览 | 系统先告诉用户现在有哪些资料、记忆和待办。 |
| 5 | 点回答前整理 | 系统把本轮要用的资料和记忆整理好，再交给助手回答。 |
| 6 | 在对话框里发问 | 用户仍然像平时一样聊天，不用跳到新页面。 |
| 7 | 打开记忆页 | 适合长期保存的内容会进入待确认区，用户确认后才保存。 |
| 8 | 展示财报案例 | 证明它能查真实资料，并生成可继续修改的报告草稿。 |
| 9 | 展示网文案例 | 证明它能找回设定、反馈和章节问题，辅助续写。 |
| 10 | 打开创作画布 | 资料和想法沉淀到画布里，最后形成可审阅的产物。 |

## 旁白口径

尽量使用这些说法：

- “知识助手”代替系统内部名称。
- “对话工作台”代替具体框架名称。
- “资料找回”代替检索术语。
- “长期记忆”代替记忆库术语。
- “待确认内容”代替审核队列术语。
- “创作画布”代替产品内部名称。

不要在字幕和配音里说这些词：

- 向量、嵌入、接口、网关、模型上下文、数据库、智能体编排。
- 系统内部英文名。
- “这是一个胶水层”这类客户不关心的表达。

## 必须拍到的效果

- 用户在对话工作台里操作知识助手入口。
- 用户能选择本轮资料范围。
- 系统能做开始前总览和回答前整理。
- 系统能按文件信息找回资料。
- 用户能直接发问，并得到带资料依据的回答。
- 长期记忆不是自动乱写，而是有待确认内容。
- 回答记录和整理任务能被追踪。
- 创作画布里能看到想法节点和产物节点，并出现财报报告或小说续写草稿。

其中创作画布不是装饰镜头。必须让客户看懂两件事：

- “想法”节点承接设定、反馈、资料线索和下一步方向。
- “产物”节点承接报告草稿、续写草稿和后续可交付内容。

## 不要拍的内容

- 不要录独立的知识助手页面作为主入口。
- 不要录历史诊断页。
- 不要打开底层数据库或底层资料库管理界面。
- 不要只放架构图。
- 不要只录命令行。

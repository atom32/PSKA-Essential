# Hermes WebUI PSKA Extension Demo

这个目录用于重做 PSKA 产品演示视频。它的产品入口是 Hermes WebUI，不是
`src/pska_essential/web/*` legacy diagnostic UI。

## 录制目标

视频展示 PSKA 的正确形态：

- Hermes WebUI 是主工作台：chat、session、settings、tool card、extension。
- PSKA 是胶水层和治理层：Product API、MCP tools、memory/review/source/trace。
- `pska-mini` 是 WebUI extension：只提供薄控制面、scope、brief、recall、投影入口。
- Eidolia 是 WebUI 内嵌创作工作区：PSKA 通过 Eidolia source/trace bridge 读取创作上下文。

## 业务 Case

1. 用户进入 Hermes WebUI，看见 PSKA extension 已加载。
2. 在 composer chip 中刷新 sidecar 状态，选择本轮知识范围。
3. 触发 Jarvis Briefing，看到 workspace、source audit、memory review 和 next actions。
4. 触发 Agentic Context Brief，看到 KB evidence、source recall、memory、trace 被组装。
5. 触发无 embedding Source Recall，展示个人文件夹/本地索引查询能力。
6. 在 Hermes chat 中发起一轮问题，PSKA scope 注入到 `knowledge-retrieval` skill。
7. 打开 PSKA Memory/Review 页面，展示 review/apply-memory gate。
8. 同步 review 到 Hermes Kanban，创建 PSKA Digest Runner task。
9. 打开 Eidolia，说明它是 WebUI 内嵌创作工作区而不是 PSKA 独立前端。

## 录制命令

脚本只生成视频和字幕，不生成 TTS 音轨。

```bash
cd /Users/xudawei/PSKA-Essential
NODE_PATH=/tmp/pska-playwright-recorder/node_modules \
HERMES_WEBUI_PASSWORD='***' \
node scripts/record_hermes_pska_extension_demo.cjs
```

默认会先把 `source_root/` 注册为只读 PSKA source root，并触发一次
metadata-first scan。这样 Source Recall 镜头可以稳定命中
`PSKA Hermes Extension Architecture` 等演示资料。

也可以录制业务 case。它们仍然从 Hermes WebUI 进入，仍然使用同一个
`pska-mini` extension，只切换 PSKA source scope、问题、Source Recall 查询和字幕：

```bash
node scripts/record_hermes_pska_extension_demo.cjs \
  --case finance_report_research \
  --detailed \
  --dwell-scale 2.5 \
  --wait-for-llm-ms 30000
```

```bash
node scripts/record_hermes_pska_extension_demo.cjs \
  --case webnovel_author \
  --detailed \
  --dwell-scale 2.5 \
  --wait-for-llm-ms 30000
```

当前内置 case：

- `core`: PSKA/Hermes WebUI extension 架构说明。
- `finance_report_research`: 金融人士的财报调研、经营风险和管理动作复盘。
- `webnovel_author`: 网文作者的 story bible、章节冲突、读者反馈和 Eidolia trace 续写。

如果已经有 Playwright storage state，可以不用密码：

```bash
HERMES_WEBUI_STORAGE_STATE=/absolute/path/hermes-storage-state.json \
node scripts/record_hermes_pska_extension_demo.cjs
```

默认连接：

```text
http://127.0.0.1:8787
```

可覆盖：

```bash
node scripts/record_hermes_pska_extension_demo.cjs \
  --base-url http://127.0.0.1:8787 \
  --pska-api-base-url http://127.0.0.1:8765 \
  --wait-for-llm-ms 45000
```

长版产品演示可以放慢每个镜头并保留更长的 Hermes chat turn：

```bash
node scripts/record_hermes_pska_extension_demo.cjs \
  --detailed \
  --dwell-scale 4 \
  --wait-for-llm-ms 75000 \
  --output-basename hermes_pska_extension_demo_long
```

如果只想录现有环境，不自动注册 demo source root：

```bash
node scripts/record_hermes_pska_extension_demo.cjs --no-seed-demo-data
```

## 输出

录制成功后会生成：

- `dist/hermes_pska_extension_demo.mp4`
- `dist/hermes_pska_extension_demo.zh.srt`
- `dist/hermes_pska_extension_demo_storyboard.zh.md`
- `dist/hermes_pska_extension_demo_manifest.json`

## 验证

```bash
python3 scripts/verify_hermes_extension_demo_pack.py
```

录完视频后强制检查媒体文件：

```bash
python3 scripts/verify_hermes_extension_demo_pack.py --require-video
```

一次检查全部已知视频：

```bash
make demo-browser-verify-videos
```

检查长版：

```bash
python3 scripts/verify_hermes_extension_demo_pack.py \
  --require-video \
  --basename hermes_pska_extension_demo_long \
  --min-duration 180
```

验证器已内置已知素材的最低时长门槛：核心短版 `30s`，核心长版 `180s`，
财报和网文业务 case `120s`。显式 `--min-duration` 只能提高门槛，不能降低这些已知素材的最低要求；
下面命令保留显式参数，是为了让验收口径在文档里一眼可见。验证器还会拒绝字幕里的英文术语，
避免后续配音或给非技术用户演示时变得难懂。

检查业务 case：

```bash
python3 scripts/verify_hermes_extension_demo_pack.py \
  --require-video \
  --case finance_report_research \
  --basename hermes_pska_finance_case_demo \
  --min-duration 120
```

```bash
python3 scripts/verify_hermes_extension_demo_pack.py \
  --require-video \
  --case webnovel_author \
  --basename hermes_pska_webnovel_case_demo \
  --min-duration 120
```

## 本机已验证素材

当前本机 `dist/` 为可再生成产物，不进入 git。最新验证结果：

- `hermes_pska_extension_demo.mp4`：`88.9s`，`1280x720`，无音轨，10 段纯中文字幕。
- `hermes_pska_extension_demo_long.mp4`：`200.8s`，`1280x720`，无音轨，10 段纯中文字幕。
- `hermes_pska_finance_case_demo.mp4`：`123.4s`，`1280x720`，无音轨，10 段纯中文字幕。
- `hermes_pska_webnovel_case_demo.mp4`：`133.5s`，`1280x720`，无音轨，10 段纯中文字幕。
- 网文 case 的 Eidolia 镜头从 `01:49.072` 到 `02:12.633`，用于展示想法/产物节点和续写草稿。

## 边界

这个 demo 不应该录：

- 独立 PSKA 前端；
- legacy diagnostic UI 作为主产品入口；
- 浏览器直连 RAGFlow、Graphiti 或数据库；
- Edge TTS 或任何自动配音。

需要讲解时使用字幕文件，后期可导入剪映。

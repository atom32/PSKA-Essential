# PSKA 组件逐步替换运行手册

日期：2026-08-20

目标：在不破坏当前可运行 PSKA 演示环境的前提下，逐步升级 RAGFlow、Hermes agent、
Hermes WebUI 和 embedding 服务形态。

## 总原则

PSKA 不直接替换所有组件，而是做控制层和治理层。外部组件可以升级、替换、旁路测试，
但入口关系不变：

```text
Hermes / Hermes WebUI / Eidolia
  -> PSKA API / PSKA HTTP MCP
  -> RAGFlow / GBrain / Graphiti / embedding / filesystem providers
```

禁止事项：

- 不新增 PSKA 独立前端。
- WebUI extension 不直接调用 RAGFlow、Graphiti 或 embedding 服务。
- 新版本组件不得默认占用旧版本端口。
- 新版本组件不得默认迁移或写入旧版本主库。
- RAGFlow v0.27 task executor 不得在队列隔离方案确认前常驻。

## 当前稳定实例

| 组件 | 当前形态 | 端口/路径 | 说明 |
|---|---|---|---|
| PSKA API | 本机 Python launchd | `127.0.0.1:8765` | 产品 API |
| PSKA MCP | HTTP MCP | `127.0.0.1:8766/mcp` | Hermes 接入入口 |
| Hermes WebUI | 本机 Python，next 代码已提升到稳定 label | `127.0.0.1:8787` | 主前端，含 PSKA extension |
| Eidolia | 本机 Node | `127.0.0.1:8797` | 创作工作台 |
| GBrain | 本机 Bun HTTP | `127.0.0.1:3131` | 当前 PSKA memory provider，HTTP MCP |
| RAGFlow stable | 源码后端 + Vite 前端 | API `9380`，Web `9222` | 当前可运行版本 |
| RAGFlow base | Docker 依赖服务 | MySQL/ES/MinIO/Redis/NATS | 不是 RAGFlow 应用容器 |
| Embedding dev | 本机 Infinity Embeddings launchd | `127.0.0.1:6380` | `BAAI/bge-m3`，MPS，label 为 `com.yuxi.infinity-emb` |
| Graphiti | Docker | `127.0.0.1:8000` | 可选图记忆候选 provider，非当前主路径 |

当前状态应优先通过统一入口查看：

```bash
scripts/pska_component_channel.sh status
```

该命令会同时显示：

- PSKA 当前 provider 选择：retrieval、KB、memory；
- PSKA API、PSKA HTTP MCP、Hermes WebUI 主入口；
- RAGFlow、GBrain、Embedding、Eidolia 等 provider；
- Graphiti、RAGFlow next、Hermes WebUI next 等可选/旁路实例。

## 当前运行形态

建议把开发机分成三种运行形态，而不是所有东西永远常驻。

### Lean dogfood

用途：日常自己使用 PSKA，辅助 ChatGPT 记忆导入、资料召回、Eidolia 创作、review 和 trace。

应常驻：

- PSKA API：`8765`
- PSKA HTTP MCP：`8766/mcp`
- Hermes WebUI：`8787`
- GBrain HTTP MCP：`3131`
- RAGFlow stable API/Web/worker：`9380/9222`
- RAGFlow Docker 依赖：MySQL、ES、MinIO、Redis/NATS
- Embedding dev：`6380`，Infinity Embeddings
- Eidolia：`8797`

应默认关闭或不常驻：

- Graphiti/Neo4j，除非正在验证图记忆 provider；
- RAGFlow v0.27 `9388/9228`；
- Hermes WebUI next `8887`。

如果 `PSKA_MEMORY_PROVIDER=gbrain`，Graphiti 容器健康与否不应影响 PSKA 主路径。省电时可以
停止 Graphiti 和 Neo4j 容器，但不要停止 RAGFlow 的 MySQL、ES、MinIO、Redis/NATS 依赖。
`scripts/start_pska_workspace.sh` 默认也不会在 GBrain dogfood 模式下自动拉起 Graphiti；
只有以下情况会启动或强制检查 Graphiti：

- `PSKA_MEMORY_PROVIDER=graphiti`
- `GRAPHITI_AUTOSTART=1`
- `scripts/start_pska_workspace.sh --with-graphiti`

省电 dry-run：

```bash
scripts/pska_component_channel.sh stop-optional
```

真正停止 optional 组件：

```bash
scripts/pska_component_channel.sh stop-optional --apply
```

只停 Graphiti/Neo4j：

```bash
scripts/pska_component_channel.sh stop-optional --component graphiti --apply
```

这个命令不会停止 PSKA API、PSKA HTTP MCP、Hermes WebUI stable、GBrain、RAGFlow stable、
embedding dev 或 Eidolia；Graphiti 使用 `docker compose down`，不会删除 Neo4j volume。

### Full demo

用途：给人演示“组件集合体系统”，需要展示可替换 provider 和图记忆候选能力。

可以额外启动：

- Graphiti/Neo4j；
- 录制脚本所需的 mock 文档、source roots 和 Eidolia demo 数据；
- 根据 demo 需要启动视频录制或浏览器视觉测试。

Full demo 仍然不允许 WebUI extension 直接调用 RAGFlow、Graphiti 或 embedding。

### Upgrade preview

用途：验证 RAGFlow v0.27 或 Hermes WebUI/agent 新版本。

只短暂启动旁路实例：

```bash
scripts/pska_component_channel.sh start-next --component ragflow --apply
scripts/pska_component_channel.sh check-next --component ragflow
scripts/pska_component_channel.sh stop-next --component ragflow --apply
```

升级预览实例不应长期占用资源，也不应默认替换 `.env.pska`。只有通过 smoke、回滚路径和
adapter 一致性检查后，才允许 promote。

当前开发机 embedding 形态：

```text
RAGFlow stable
  -> http://localhost:6380
  -> Infinity Embeddings
  -> BAAI/bge-m3
  -> Apple Silicon MPS
```

交付环境 embedding 形态：

```text
RAGFlow container
  -> http://pska-embedding:80
  -> TEI embedding container
  -> default BAAI/bge-small-en-v1.5
```

因此 embedding 已经天然是 provider 形态。当前不要把开发机强行改成 TEI 镜像，除非要验证交付包。

### Embedding 组件契约

PSKA 当前把 embedding 作为 RAGFlow 侧组件建模，而不是 PSKA/Hermes/WebUI 的直接依赖。

```text
Hermes / WebUI
  -> PSKA API / PSKA HTTP MCP
  -> RAGFlow
  -> embedding provider
```

已落地的只读状态：

- `workspace_status.components.embedding.schema = pska.embedding_component_status.v1`
- `GET /api/components/embedding`
- `GET /api/runtime/diagnostics` 的 `components.embedding`
- 开发机模式：`local_infinity_dev`
- 交付模式：`tei_container_delivery`
- 允许的调用路径：`Hermes/WebUI -> PSKA -> RAGFlow -> embedding`
- 禁止的调用路径：`Hermes/WebUI -> embedding`

本机开发环境可以继续用 `com.yuxi.infinity-emb` 和 `127.0.0.1:6380`。给别人部署时，
`deploy/full-compose` 仍启动 TEI 镜像，RAGFlow 通过 Docker 私有网络访问
`http://pska-embedding:80`。这两种形态共享同一个 PSKA component status，不再是两套互相
看不见的说明。

Hermes WebUI extension 跟进：

- PSKA-mini dashboard 使用 compact workspace status：
  `GET /api/workspace/status?compact=1&view=webui&next_action_limit=8`
- chip 菜单显示 `Embedding` 状态。
- PSKA Memory 页面顶部显示 `Embedding` 状态。
- contract test 覆盖 sidecar 的 `GET /api/components/embedding`。
- Playwright 视觉 smoke 覆盖桌面菜单、移动菜单和 Memory 页面里的 Embedding 状态。

## RAGFlow v0.27 旁路状态

旁路目录：

```bash
/Users/xudawei/PSKA-Components/ragflow-v0.27.0
```

当前 tag：

```text
v0.27.0
```

已完成：

- 新建官方 `v0.27.0` checkout。
- 迁移 PSKA 的 `priority` 补丁。
- 增加 Vite 代理目标环境变量，避免 v0.27 Web 打到旧 API。
- 增加旁路启动脚本：
  - `pska-run-ragflow-server-v027.sh`
  - `pska-run-ragflow-web-v027.sh`
  - `pska-prepare-v027-db.sh`
  - `pska-run-ragflow-task-executor-v027.sh`
  - `pska-seed-v027-dev-user.sh`
- 修改旁路 `conf/service_conf.yaml`：
  - API `9388`
  - Admin `9389`
  - MySQL DB `rag_flow_027`
  - Redis DB `2`
- 已创建空实验库 `rag_flow_027`。
- 已安装 v0.27 隔离 Python 依赖，`.venv` 使用 CPython `3.13.14`。
- 已安装 v0.27 Web 依赖。
- `npm run build` 已通过，证明生产前端可构建。
- 已短暂启动 v0.27 API，`GET /api/v1/system/ping` 在 `9388` 返回 `pong`。
- 已确认 v0.27 task queue 使用 Redis Stream；旁路用 Redis DB `2` 与稳定实例 DB `1`
  隔离。
- 已 seed v0.27 本地开发用户、API token 和
  `bge-m3@local-infinity-direct@SILICONFLOW` embedding 绑定，只写入
  `rag_flow_027`。
- 已用 PSKA `RagflowKnowledgeGateway` 对 v0.27 做 live smoke：
  - list dataset；
  - create dataset；
  - upload Markdown；
  - `parse_documents(priority=1)`。
- 已启动一次 v0.27 手动 worker，确认它在 Redis DB `2` 接到任务，并完成解析、embedding
  和 ES 索引。
- 已用 PSKA `RagflowRetrievalAdapter` 对 v0.27 检索，返回规范化
  `ContextPacket/SourceRef`。
- 已修复 v0.27 seed 用户密码格式：
  - RAGFlow 登录校验使用前端解密后的 base64 密码；
  - seed 脚本现在与 `api/db/init_data.py:init_superuser` 保持一致；
  - 重复执行会幂等刷新候选用户密码。
- 已做 v0.27 WebUI 旁路浏览器级检查：
  - API `9388` 启动成功；
  - Web `9228` 启动成功；
  - `9228/api/v1/system/ping` 经 Vite proxy 返回 `pong`；
  - 浏览器登录 seed 用户成功；
  - 登录后首页显示 smoke 数据集；
  - 截图证据：`/tmp/pska-ragflow-v027-web-20260820.png`。
- smoke 后已停掉 v0.27 API 和 worker，`9388`/`9228` 未常驻，旧 `9380` 仍健康。

未完成：

- v0.27 后端尚未作为常驻服务启动。
- v0.27 还没有替换稳定 `9380/9222`。
- 还没有把 PSKA 正式运行环境的 `RAGFLOW_BASE_URL` 指向 `9388`；目前只做过临时环境变量烟测。

已知校验结果：

- `python3 -m py_compile` 已通过。
- `bash -n pska-run-ragflow-server-v027.sh pska-run-ragflow-web-v027.sh
  pska-prepare-v027-db.sh pska-run-ragflow-task-executor-v027.sh
  pska-seed-v027-dev-user.sh` 已通过。
- 首次 API smoke 暴露 macOS Bash 3.2 不支持 `${var,,}` 的问题，已在旁路
  `docker/launch_backend_service.sh` 中改为 `tr` 小写转换。
- `npm run type-check` 未通过，但错误来自 v0.27 上游前端大量既有严格类型问题；
  当前 PSKA 的 Vite 代理补丁不在报错列表中。
- `npm run build` 已通过。
- v0.27 Web 旁路浏览器 smoke 已通过。

## RAGFlow v0.27 验证顺序

先确认旧实例健康：

```bash
curl http://127.0.0.1:9380/api/v1/system/ping
curl http://127.0.0.1:6380/health
```

准备 v0.27 实验库：

```bash
cd /Users/xudawei/PSKA-Components/ragflow-v0.27.0
./pska-prepare-v027-db.sh
./pska-seed-v027-dev-user.sh
```

只启动 v0.27 API 时，预期端口：

```text
http://127.0.0.1:9388
```

只启动 v0.27 Web 时，预期端口：

```text
http://127.0.0.1:9228
```

切换 PSKA adapter 前必须验证：

- `GET /api/v1/system/ping` 返回健康。
- 有候选 API key；本机候选环境可由 `pska-seed-v027-dev-user.sh` 幂等创建。
- 可以创建测试 dataset。
- 可以上传一个小文件。
- 不启动 task executor 时，系统不会误判为 ready。
- 一旦解析需要 worker，先解决队列隔离，再启动 v0.27 worker。
- PSKA readiness 可以显示解析/索引未完成，而不是机械 fallback。

本轮已完成的候选闭环：

```text
PSKA backend adapter
  -> RAGFlow v0.27 API 9388
  -> Redis DB 2 queue
  -> v0.27 worker
  -> local embedding 6380
  -> Elasticsearch index
  -> PSKA retrieval adapter
  -> ContextPacket / SourceRef
```

## Hermes Agent 旁路升级原则

旧稳定目录，也就是回滚来源：

```bash
/Users/xudawei/.hermes/hermes-agent
```

旧稳定 commit：

```text
db27f1a1
```

当前稳定运行目录已经切到：

```bash
/Users/xudawei/PSKA-Components/hermes-agent-next
```

当前运行 commit：

```text
d3e1246
```

当前稳定服务：

```text
com.pska.hermes-webui
```

后续验证仍使用 next 目录，不直接覆盖旧稳定目录：

```bash
cd /Users/xudawei/PSKA-Components/hermes-agent-next
```

验证目标：

- HTTP MCP 连接仍指向 `http://127.0.0.1:8766/mcp`。已用
  `hermes-agent-next` 源码读取当前配置确认。
- 不恢复 stdio MCP。已确认 `pska-essential` 解析为 `transport=http`，没有
  `command`。
- PSKA tools 能列出、调用、返回结构化错误。
- Agent 对 PSKA 内部流程只做进出数据处理，不直接写 memory、source 或 RAGFlow。
- WebUI extension 发起的请求仍只进 PSKA。

已完成轻量检查：

- `hermes-agent-next` commit 为 `d3e1246`。
- 已按 Hermes README 建立源码目录外的独立候选 venv：
  - `/Users/xudawei/.hermes/venvs/hermes-agent-next`
  - Python `3.11.15`
  - 安装范围：核心依赖 + MCP extra
  - 当前体积约 `105M`
- 使用稳定 agent venv 导入候选源码入口成功：
  - `run_agent`
  - `hermes_cli.main`
  - `tools.mcp_tool`
  - `hermes_cli.mcp_config`
  - `hermes_cli.mcp_startup`
- 使用稳定 agent venv 编译候选入口成功：
  - `run_agent.py`
  - `hermes_cli/main.py`
  - `tools/mcp_tool.py`
  - `hermes_cli/mcp_config.py`
  - `hermes_cli/mcp_startup.py`
- 使用独立候选 venv 导入、编译上述入口成功。
- 使用独立候选 venv 运行 `hermes --help` 成功。
- 使用独立候选 venv 运行 Hermes MCP 检查成功：
  - `hermes mcp list` 显示 `pska-essential` 为 enabled；
  - transport 为 `http://127.0.0.1:8766/mcp`；
  - `hermes mcp test pska-essential` 连接成功；
  - 工具发现数量：`109`。
- next WebUI 已复测使用独立候选 venv 启动，启动日志显示：
  `python: /Users/xudawei/.hermes/venvs/hermes-agent-next/bin/python`。

当前主线状态：

- `com.pska.hermes-webui` 已切到 `hermes-agent-next`，稳定端口仍是 `8787`。
- 旧 WebUI/agent 没有被删除，可通过备份 plist 回滚。
- 回滚备份：
  `/Users/xudawei/.hermes/pska-channel-backups/20260820-210101/com.pska.hermes-webui.plist`。
- 已用 next agent 发起真实 LLM turn，并确认模型通过 HTTP MCP 调用了 PSKA 工具。

### Hermes 真实 agent turn 证据

已完成一次真实 `hermes chat` 检查，要求 agent 只调用 PSKA 只读工具。

结果：

- session id：`20260820_212734_89b9fa`。
- 使用模型：`deepseek-v4-flash`。
- PSKA MCP server 注册成功，日志中显示 HTTP MCP 工具已发现。
- 模型实际调用：
  - `pska_workspace_status`
  - `pska_memory_health_scan`
- 结果判断：
  - MCP 连通；
  - memory provider 为 `gbrain`；
  - KB/RAG provider 为 `ragflow`；
  - `dev_fake=false`；
  - 当前 memory card 数量为 `10`；
  - memory health 未发现 quality/stale/conflict 问题。

这次检查同时暴露一个真实工程问题：

```text
pska_workspace_status full view 约 386KB
```

对于 WebUI 诊断页，这是可接受的完整视图；但对于 Hermes agent，这是过大的上下文包，
会增加 token、耗电和工具解析负担。因此已增加 agent-facing compact view：

```bash
PYTHONPATH=src .venv/bin/python -m pska_essential.workspace_status_cli \
  --env-file .env.pska \
  --compact \
  --next-action-limit 3
```

本机实测：

```text
compact workspace_status 约 6.9KB
full workspace_status    约 386KB
```

PSKA API 重启后实测：

```text
GET /api/workspace/status?compact=1 约 5.4KB
GET /api/workspace/status           约 270KB
```

Hermes compact turn 复测：

- session id：`20260820_213943_38af95`。
- `pska_workspace_status(compact=true,next_action_limit=3)` 调用成功。
- Hermes 日志中该工具结果约 `7657` chars。
- 同一 turn 再调用 `pska_memory_health_scan` 成功。
- turn 在 `3/5` API call 内正常结束，不再因为解析超大状态包撞到 max iterations。

compact 改动后 WebUI 主入口补充回归：

- `make webui-extension-contract` 已通过。
- 合同测试结果：`29/29` 通过。
- 覆盖登录、extension manifest/JS/CSS、sidecar health、workspace status、KB datasets、
  runtime diagnostics、RAGFlow Probe、Preview、Jarvis Brief、Agentic Brief、Source Recall、
  Memory Search、Review Queue、Kanban projection、Digest Task 和 Chat bridge skill content。
- 浏览器级视觉 smoke 已通过，使用 `playwright-core` + Chrome channel。
- 视觉输出目录：
  `/var/folders/96/kqt4bhy12rs4sx3c0bsj03wm0000gp/T/pska-webui-visual-2026-08-20T13-42-55-236Z`。
- 视觉覆盖桌面菜单、Source Recall、Memory 页面、移动端 PSKA chip、移动端菜单。
- 控制台 warning/error：`0`。

新合同：

- 默认 `pska_workspace_status()` 不变，仍返回完整 `workspace_status`。
- MCP 可用 `pska_workspace_status(compact=true)` 或 `view="agent"` 请求
  `workspace_status_compact`。
- Product API 可用 `/api/workspace/status?compact=1` 或
  `/api/workspace/status?view=agent` 请求 compact view。
- CLI 可用 `--compact`。
- compact view 保留 provider、workspace、governance、GBrain 参与状态、memory/card/health
  数量、KB ready/blocked 计数和 next actions。
- compact view 省略完整 datasets、dataset readiness、memory cards、memory health issues、
  review/workflow/job 明细；agent 需要细节时再调用专门工具。

## Hermes WebUI 旁路/主线升级状态

旧稳定目录，也就是回滚来源：

```bash
/Users/xudawei/hermes-webui
```

旧稳定 commit：

```text
320789ae
```

当前稳定运行目录已经切到：

```bash
/Users/xudawei/PSKA-Components/hermes-webui-next
```

当前运行 commit：

```text
1f5e4552
```

稳定 launchd label 仍然是：

```text
com.pska.hermes-webui
```

已完成轻量检查：

- 旁路浅克隆成功。
- `python3 -m py_compile server.py bootstrap.py mcp_server.py` 通过。
- 已增加旁路脚本：
  - `/Users/xudawei/PSKA-Components/hermes-webui-next/pska-sync-extension-next.sh`
  - `/Users/xudawei/PSKA-Components/hermes-webui-next/pska-run-hermes-webui-next.sh`
  - `/Users/xudawei/PSKA-Components/hermes-webui-next/pska-check-hermes-webui-next.sh`
- 已用旁路脚本启动 next WebUI：
  - `HERMES_WEBUI_PORT=8887`
  - `HERMES_WEBUI_STATE_DIR=~/.hermes/webui-next`
  - `HERMES_WEBUI_AGENT_DIR=/Users/xudawei/PSKA-Components/hermes-agent-next`
  - Python 解释器优先使用候选 agent venv：
    `~/.hermes/venvs/hermes-agent-next/bin/python`
- 已确认 next WebUI `/health` 正常。
- 已确认 next WebUI `/api/extensions/status` 中：
  - `pska-mini` 有效启用；
  - `pska-mini` script/style 通过 `/extensions/pska-mini/...` 注入；
  - `pska-mini` sidecar origin 为 `http://127.0.0.1:8765`；
  - sidecar consent 已写入 `~/.hermes/webui-next/extension-overrides.json`。
- 已确认 `pska-mini` sidecar 代理能访问 PSKA `/api/health`。
- 已做浏览器级视觉检查：
  - 页面中出现 PSKA-mini 面板；
  - 状态显示 `API ready / KB 10/10 / Memory gbrain / GBrain active`；
  - 能看到 RAGFlow 数据集列表；
  - 截图证据：`/tmp/pska-hermes-webui-next-pska-mini-20260820.png`。
- 已修复 PSKA-mini 在 in-app browser 中请求失败的问题：
  - 原因：候选浏览器环境中 `window.fetch` 不可用；
  - 处理：PSKA-mini 请求层增加 `XMLHttpRequest` fallback；
  - 修复位置：`integrations/hermes-webui-extension/pska-mini/pska-mini.js`。
- 已执行 `promote-hermes-next --apply`，把稳定 `8787` 切到 next WebUI/agent：
  - `WorkingDirectory=/Users/xudawei/PSKA-Components/hermes-webui-next`；
  - `HERMES_WEBUI_AGENT_DIR=/Users/xudawei/PSKA-Components/hermes-agent-next`；
  - `HERMES_WEBUI_PYTHON=/Users/xudawei/.hermes/venvs/hermes-agent-next/bin/python`；
  - 启动前自动执行 `pska-sync-extension-next.sh` 同步 PSKA extension；
  - 复跑 promote 时不会覆盖第一次生成的旧版回滚备份。
- 已在稳定端口 `8787` 做认证后的 WebUI extension 检查：
  - 未登录访问 `/api/extensions/status` 返回 `401`；
  - 登录后 `pska-check-hermes-webui-next.sh` 检查通过；
  - PSKA extension 面板显示 `API ready / Memory gbrain / KB 10/10 / GBrain active`；
  - 截图证据：`/tmp/pska-hermes-promoted-8787-post-restart-20260820.png`。

旁路端口建议：

```text
stable WebUI: 8787, 当前已运行 next 代码
next WebUI:  8887, 只在需要并行对照时临时启动
```

验证目标：

- PSKA extension 能加载。已通过。
- extension 页面覆盖当前已有功能点。
- extension 不出现独立 PSKA 前端入口。已通过。
- extension 不直接调用 RAGFlow、Graphiti、embedding。已通过静态检查；请求入口仍是
  `/api/extensions/pska-mini/sidecar/...` 到 PSKA API。
- 浏览器级视觉测试通过。已通过。

旁路启动：

```bash
cd /Users/xudawei/PSKA-Components/hermes-webui-next
./pska-run-hermes-webui-next.sh
```

旁路检查：

```bash
cd /Users/xudawei/PSKA-Components/hermes-webui-next
./pska-check-hermes-webui-next.sh
```

检查通过时，预期输出类似：

```text
Hermes WebUI next basic PSKA checks passed at http://127.0.0.1:8887
```

稳定端口检查时需要使用现有 WebUI 认证状态或提供本机检查密码；不要把密码写入仓库。

## 组件切换控制脚本

已增加统一脚本：

```bash
/Users/xudawei/PSKA-Essential/scripts/pska_component_channel.sh
```

用途：

- 查看稳定线和候选线状态。
- 启停旁路 RAGFlow v0.27、RAGFlow v0.27 Web、RAGFlow v0.27 worker。
- 启停旁路 Hermes WebUI next。
- 将稳定 Hermes WebUI launchd job 切到 next WebUI/agent。
- 将 PSKA `.env.pska` 的 RAGFlow 指向旁路 v0.27。
- 从自动备份回滚 Hermes WebUI plist 或 `.env.pska`。

安全边界：

- `status` 和 `check-next` 只读。
- `start-next`、`stop-next`、`promote-*`、`rollback-*` 默认只干跑。
- 真正执行必须加 `--apply`。
- `promote-ragflow-next --apply` 必须显式提供 `RAGFLOW_NEXT_API_TOKEN`，脚本不会把候选
  API key 写死进主仓库。
- RAGFlow next 默认仍在 `9388/9228`，不占稳定 `9380/9222`。
- Hermes WebUI next 的旁路模式默认仍在 `8887`；当前主线已经把稳定 `8787` 指到 next 代码。
- 切换脚本不创建 PSKA 独立前端。

当前已验证：

```bash
bash -n scripts/pska_component_channel.sh
PYTHONPATH=src python3 -m unittest tests.test_component_channel_script tests.test_hermes_webui_extension tests.test_adapters
PYTHONPATH=src python3 -m unittest tests.test_workspace_status tests.test_workspace_status_cli tests.test_mcp_contract tests.test_product_api
scripts/pska_component_channel.sh status
scripts/pska_component_channel.sh start-next --component hermes
scripts/pska_component_channel.sh start-next --component ragflow --with-worker
scripts/pska_component_channel.sh promote-hermes-next --apply
scripts/pska_component_channel.sh promote-ragflow-next --no-restart-pska
```

验证结果：

- 单元测试 `22` 个通过。
- workspace status/API/MCP/CLI 相关单元测试 `143` 个通过。
- 当前稳定线健康。
- 候选线没有常驻。
- dry-run 命令不会改 launchd、不会改 `.env.pska`、不会重启 PSKA。
- `--apply` 旁路启动已验证：
  - `com.pska.hermes-webui.next` 启动成功；
  - `com.pska.ragflow.next` 启动成功；
  - `com.pska.ragflow.web.next` 启动成功；
  - `com.pska.ragflow.task-executor.next` 启动成功；
  - `check-next --component all` 通过；
  - Hermes WebUI next 的 PSKA extension sidecar 检查通过。
- RAGFlow v0.27 launchd 路径已做真实 PSKA adapter smoke：
  - 临时 dataset 创建成功；
  - Markdown 上传成功；
  - `priority=1` parse 成功；
  - worker 将文档解析到 `DONE`；
  - `chunk_count=1`；
  - PSKA `RagflowRetrievalAdapter` 用 smoke marker 检索到 `1` 个 context packet；
  - 临时 dataset 删除成功。
- `stop-next --component all --with-worker --apply` 已验证：
  - 候选 `9388/9228/8887` 端口释放；
  - 候选 launchd label 全部卸载；
  - 稳定线 `8787/9380/9222/8765/8766` 仍健康。
- `promote-hermes-next --apply` 已验证：
  - 稳定 `com.pska.hermes-webui` label 保持不变；
  - 稳定端口 `8787` 改为运行 `hermes-webui-next` 和 `hermes-agent-next`；
  - WebUI extension 自动同步；
  - 原稳定 plist 已保存在回滚目录；
  - PSKA MCP 仍为 HTTP 连接，工具发现数量 `109`。
- WebUI extension 视觉 smoke 已固化为脚本：
  - `scripts/test_pska_webui_visual.cjs`；
  - 默认输出到 `/tmp/pska-webui-visual-*`；
  - 不把 Playwright 作为 PSKA 主包依赖；
  - 可通过 `make webui-extension-visual` 运行。
- WebUI extension 合同测试已复跑通过：
  - `scripts/test_pska_webui_extension.mjs`；
  - `29/29` 项通过；
  - 覆盖 sidecar、RAGFlow Probe、Preview、Jarvis Brief、Agentic Brief、Source Recall、
    Memory Search、Review Queue、Kanban projection、Digest Task；
  - Kanban 临时投影会自动归档。
- promoted `8787` 主线端口已跑过真实视觉 smoke：
  - 输出目录：`/tmp/pska-webui-visual-promoted-8787-20260820-212115`；
  - 结果：`ok=true`；
  - 覆盖：桌面菜单、Source Recall、Memory Page、手机 chip、手机菜单；
  - 控制台 warning/error：`0`。
- 停止脚本已加强：
  - 先按 service target bootout；
  - 再按 plist bootout；
  - 等待候选 label 真正消失，避免 worker 停止延迟造成误判。

## 演示素材入口纠偏

旧 `demo/browser/pska_webui_demo` 是历史 Product API 诊断页素材，不再作为产品演示。
已完成以下整理：

- 旧诊断页 README、package、evidence matrix、剪映说明和 `report.html` 都改为禁用说明。
- 旧录制、构建、旁白、打包、验证脚本都改为短 stub，执行时会明确提示改用 Hermes WebUI
  extension demo。
- 旧诊断页截图、视频、字幕、manifest、storyboard、source fixture 已从 git 跟踪中移除。
- `make demo-browser-verify` 已改为验证 Hermes WebUI extension demo。
- 新的可复现演示源文件进入仓库：
  - `demo/browser/hermes_pska_extension_demo/README.zh.md`
  - `demo/browser/hermes_pska_extension_demo/FEATURE_EVIDENCE_MATRIX.zh.md`
  - `demo/browser/hermes_pska_extension_demo/demo_plan.json`
  - `demo/browser/hermes_pska_extension_demo/source_root/`
  - `demo/browser/hermes_pska_extension_demo/cases/`
  - `scripts/record_hermes_pska_extension_demo.cjs`
  - `scripts/verify_hermes_extension_demo_pack.py`
- 新 demo 的 `dist/` 仍然是本机生成产物，不进仓库。

已验证：

```bash
python3 scripts/verify_hermes_extension_demo_pack.py
make demo-browser-verify
make demo-browser-verify-videos
python3 scripts/verify_hermes_extension_demo_pack.py --require-video
python3 scripts/verify_hermes_extension_demo_pack.py --all-videos
python3 scripts/verify_hermes_extension_demo_pack.py --require-video --basename hermes_pska_extension_demo_long --min-duration 180
python3 scripts/verify_hermes_extension_demo_pack.py --require-video --case finance_report_research --basename hermes_pska_finance_case_demo --min-duration 120
python3 scripts/verify_hermes_extension_demo_pack.py --require-video --case webnovel_author --basename hermes_pska_webnovel_case_demo --min-duration 120
```

验证器本身已内置最低时长门槛：核心短版 `30s`，核心长版 `180s`，财报和网文业务 case
`120s`。因此漏写或误写较低的 `--min-duration` 时，已知业务 case 不会退回到 30 秒通过。

本机视频验证结果：

- core demo：`60.9s`，`1280x720`，无音轨，10 段字幕。
- long core demo：`190.2s`，`1280x720`，无音轨，10 段字幕。
- finance case：`123.4s`，`1280x720`，无音轨，10 段字幕。
- webnovel case：`133.5s`，`1280x720`，无音轨，10 段字幕；Eidolia 镜头保留
  `23.6s`，展示想法/产物两类节点与续写草稿。

## 当前开发环境结论

截至本次检查，开发机处于以下状态：

```text
稳定线：
  Hermes WebUI        8787, next 代码已提升到稳定 label
  Hermes agent        hermes-agent-next, 独立 venv
  PSKA API            8765
  PSKA HTTP MCP       8766/mcp
  RAGFlow API         9380
  RAGFlow Web         9222
  RAGFlow worker      launchd 常驻
  Embedding           6380, Infinity Embeddings, bge-m3, MPS, com.yuxi.infinity-emb
  Eidolia             8797
  GBrain              3131, 当前 memory provider
  Graphiti            8000, Docker，可选，不是当前主路径

候选线：
  RAGFlow v0.27 API   9388, 已 smoke，通过后停止
  RAGFlow v0.27 Web   9228, 已浏览器 smoke，通过后停止
  Hermes WebUI next   8887, 只作为临时并行对照，不常驻
  Hermes agent next   已切主线，仍可用旧 agent 回滚
```

embedding 分层：

- 开发机现在用本机 Infinity Embeddings，方便调试、速度快、和 RAGFlow stable/v0.27 都能复用。
- `deploy/full-compose/docker-compose.yml` 中已有 `embedding` profile，默认使用
  `ghcr.io/huggingface/text-embeddings-inference:cpu-1.8`。
- 交付时 embedding 是镜像服务，容器网络别名为 `pska-embedding`，默认模型为
  `BAAI/bge-small-en-v1.5`，宿主映射仍可用 `6380`。
- 所以当前不需要把开发机强行切成容器 embedding；需要验证交付包时再启用 compose profile。
- 已增加 full-compose 只读预检：

  ```bash
  ./bootstrap.sh preflight
  make full-compose-preflight
  ```

  预检不 clone、不写 runtime、不启动容器，只检查 Docker、WebUI/Gateway 基础安全、
  TEI embedding profile 和宿主端口。
- 在当前开发机上用交付默认端口跑预检，正确报出 3 个阻断冲突：
  - `6380`：已被本机 Infinity Embeddings 占用；
  - `8787`：已被本机 Hermes WebUI 主线占用；
  - `9380`：已被本机 RAGFlow stable API 占用。
- 这意味着 full-compose 交付包应在干净交付机上启动；如果要在开发机上并行验证，需要先改
  `.env` 里的 `EMBEDDING_HOST_PORT`、`HERMES_WEBUI_PORT`、`RAGFLOW_HOST_PORT` 等端口，
  或停止对应开发服务。

当前 lean dogfood 结论：

- `PSKA_MEMORY_PROVIDER=gbrain`，GBrain HTTP MCP 是主路径。
- Graphiti/Neo4j 只在验证图记忆 provider 时需要；否则可以停掉来省电。
- RAGFlow next 和 Hermes WebUI next 只做旁路验证，不应常驻。
- `scripts/pska_component_channel.sh status` 是判断当前机器处于哪种运行形态的第一入口。

## 切换门槛

一个组件只有同时满足以下条件，才允许替换稳定实例：

- 当前稳定实例可恢复。
- 新实例有独立端口或独立目录。
- 关键路径 live smoke 通过。
- PSKA adapter 行为一致或更好。
- 日志能定位失败来源。
- 没有破坏 Hermes WebUI extension 作为主入口的规则。
- 没有把非确定性 agent 放到 PSKA 内部治理流程的核心位置。

## 下一步

1. 用真实 LLM turn 再跑一次 Hermes agent/WebUI 主线检查；MCP 连接和工具发现已经单独通过。
2. 选择 RAGFlow v0.27 的切换策略：
   - 短期：PSKA `.env.pska` 指向 `9388`，旧 `9380` 保留回滚。
   - 中期：v0.27 迁回稳定端口，旧目录归档。
3. 做 PSKA adapter 双实例切换变量：

   ```bash
   RAGFLOW_BASE_URL=http://127.0.0.1:9388
   ```

4. 把 `webui-extension-visual` 纳入后续主线回归清单；本轮 promoted `8787` 已通过一次。
5. 验证交付用 embedding 镜像 profile，确认它和开发机 Infinity 的 API 行为一致。

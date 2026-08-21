# PSKA Alpha 验收快照

日期：2026-08-21

## 结论

当前本机 dogfood 实例达到 `alpha_ready`，并且 Hermes WebUI 扩展、浏览器级视觉检查、真实发问注入、完整组件闭环和四段演示视频都已重新验证。

```text
alpha_readiness.status = alpha_ready
check_count = 10
pass_count = 10
warn_count = 0
fail_count = 0
required_failure_count = 0
```

这表示当前实例适合 owner dogfooding 和有引导的技术 alpha。它仍不表示可以无提示写回用户源文件，也不表示备份、恢复或清理动作会自动执行。

## 当前运行链路

```text
Hermes WebUI extension
  -> PSKA Product API / PSKA HTTP MCP
    -> RAGFlow KB / retrieval
    -> GBrain memory over HTTP MCP
    -> PSKA Review / audit ledger
    -> Eidolia sidecar
```

当前 provider：

```text
retrieval = ragflow
kb        = ragflow
memory    = gbrain
embedding = local_infinity_dev, BAAI/bge-m3
Graphiti  = OFF optional, not selected
```

## Alpha Gate 证据

命令：

```bash
make alpha-acceptance ENV_FILE=.env.pska PYTHON=.venv/bin/python
```

结果：

```text
Status: ok
alpha_readiness       PASS status=alpha_ready
live_connectivity     PASS status=ok mode=connectivity_only
full_component_proof  PASS status=ok mode=full_component_proof
```

完整组件闭环使用的 ready dataset：

```text
dataset_id = 07f35e1a9b9411f197ff8391030412c0
```

闭环输出摘要：

```text
run_id                  = run_9a450e5402e24ab195589f42627ad107
retrieval_context_count = 2
closed_loop_contexts    = 4
closed_loop_sources     = 9
source_inspection_count = 2
exported                = true
```

这证明当前实例可以完成：

```text
ready scope 检查
RAGFlow 检索
GBrain 记忆探针
Agentic Ask
源片段读取
可追溯导出
审计记录写入
```

## Hermes WebUI Extension 证据

命令：

```bash
NODE_PATH=/tmp/pska-playwright/node_modules \
PSKA_PLAYWRIGHT_MODULE=playwright-core \
PSKA_PLAYWRIGHT_CHANNEL=chrome \
HERMES_WEBUI_PASSWORD=****** \
make alpha-acceptance-webui ENV_FILE=.env.pska PYTHON=.venv/bin/python
```

结果：

```text
Status: ok
webui_extension_contract    PASS passed=41/41
webui_extension_visual      PASS ok=True
webui_extension_turn_bridge PASS ok=True forced_context_count=1
```

契约测试覆盖：

```text
WebUI login
extension manifest/js/css
sidecar health
workspace status
embedding component
KB datasets
runtime diagnostics
job health
wakeup plan
observability metrics
source recall eval
alpha readiness
alpha first-run session/checklist update
Hermes profile/projects/workspaces
RAGFlow probe
memory-only preview
dataset-scoped preview
Jarvis Brief
Agentic Brief
Source Recall
Memory search/review/proof/trace
Kanban projection
Digest task
chat bridge skill dependency
```

浏览器级视觉检查确认：

```text
desktop menu visible and in viewport
desktop Source Recall returns visible results
desktop Agentic Brief shows specialist profiles
Memory page visible with memory and review data
Source Evidence search/read/draft works through PSKA
Answer Proof detail shows trace and tools
First-run checklist reaches ready-for-repetition 8/8
mobile PSKA chip visible and not overlapping send
mobile menu visible and in viewport
console warnings/errors = 0
```

真实发问注入链路确认：

```text
PSKA runtime bridge is installed
selected dataset and source root are included
Hermes /api/chat/start is intercepted
forced PSKA skill context is injected
visible user turn remains clean
message_length = 10417
forced_context_count = 1
```

这证明 `pska-mini` 不只是状态面板；当用户在 Hermes WebUI 里真实发送问题时，它会把本轮 PSKA 资料范围和工具约束注入到 Hermes 的请求中，同时聊天窗口仍显示干净的原始用户问题。

## 演示视频证据

命令：

```bash
make demo-browser-verify-videos
```

结果：

```text
hermes_pska_extension_demo.mp4       88.9s   1280x720 no audio 10 ordered plain Chinese subtitles
hermes_pska_extension_demo_long.mp4  200.8s  1280x720 no audio 10 ordered plain Chinese subtitles
hermes_pska_finance_case_demo.mp4    123.4s  1280x720 no audio 10 ordered plain Chinese subtitles
hermes_pska_webnovel_case_demo.mp4   133.5s  1280x720 no audio 10 ordered plain Chinese subtitles
```

演示包验证器同时检查：

```text
Hermes WebUI entrypoint
10 个演示镜头
无自动配音
功能证据矩阵覆盖全部镜头
功能证据矩阵使用纯中文讲法
字幕使用纯中文讲法
历史诊断页演示路径被禁用
```

这些视频只展示 Hermes WebUI extension 路径，不把 PSKA 包装成独立产品前端。

## 记忆治理状态

当前 memory provider：

```text
backend = gbrain
```

当前治理边界：

```text
conversation_memory = auto_apply
durable_memory      = manual_review
digest_memory       = manual_review
review_queue_role   = exception_inbox
```

GBrain 当前能力边界：

```text
search = supported
list   = supported
apply  = supported
delete = supported
get    = not provider-neutral direct lookup
update = use append_correction_episode policy for now
```

这意味着普通对话里的明确记忆增删改可以走受控入口；批量、来源派生、冲突或风险较高的长期记忆仍要进入 Review。

## 边界

当前可以演示和 dogfood 的能力：

```text
Hermes WebUI extension 作为唯一用户入口
PSKA Product API / HTTP MCP 作为边界
RAGFlow ready dataset 检索和 Ask
GBrain 记忆检索和治理写入路径
Memory Review queue
Source Evidence -> memory candidate
Agentic Context Brief / Jarvis Brief
Source Recall
Eidolia 创作场景与 trace/source bridge
Alpha trial guide / recovery plan / first-run checklist
四段浏览器操作演示视频
```

仍保持锁定或可选的能力：

```text
Graphiti 是 optional，当前不在主链路
native source writeback 需要备份确认
duplicate cleanup 仍是 proposal/review-only，不执行删除、移动或合并
provider backups 和 rollback 需要人工演练
RAGFlow next / Hermes WebUI next 是 side-by-side optional，不影响主线
```

## 验收命令清单

推荐入口：

```bash
make alpha-acceptance ENV_FILE=.env.pska PYTHON=.venv/bin/python
```

产品边界守门：

```bash
make product-boundary-contract
```

演示前完整入口，包含 Hermes WebUI extension 契约、浏览器级视觉检查和真实发问注入：

```bash
NODE_PATH=/tmp/pska-playwright/node_modules \
PSKA_PLAYWRIGHT_MODULE=playwright-core \
PSKA_PLAYWRIGHT_CHANNEL=chrome \
HERMES_WEBUI_PASSWORD=****** \
make alpha-acceptance-webui ENV_FILE=.env.pska PYTHON=.venv/bin/python
```

演示视频证据：

```bash
make demo-browser-verify-videos
```

基础回归：

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

最近一次结果：

```text
alpha-acceptance          OK
product-boundary-contract OK
alpha-acceptance-webui    OK, 41/41 contract, visual OK, turn bridge OK
demo-browser-videos       OK, 4/4 videos, pure Chinese subtitles
unittest                  513 tests OK
```

所有 alpha acceptance 原始 JSON 证据写入 `/tmp/pska-alpha-acceptance-*`，不写入仓库，也不保存密码或 provider token。

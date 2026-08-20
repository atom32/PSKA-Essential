# PSKA Alpha 验收快照

日期：2026-08-20

## 结论

当前本机 dogfood 实例达到 `alpha_ready`：

```text
alpha_readiness.status = alpha_ready
check_count = 10
pass_count = 10
warn_count = 0
fail_count = 0
required_failure_count = 0
```

这表示当前实例适合 owner dogfooding 和有引导的技术 alpha。它不表示已经可以无提示地写回用户源文件，也不表示备份/恢复会自动执行。

## 当前运行链路

```text
Hermes WebUI extension
  -> PSKA Product API / PSKA HTTP MCP
    -> RAGFlow KB / retrieval
    -> GBrain memory over HTTP MCP
    -> PSKA Review / audit ledger
    -> Eidolia sidecar
```

当前状态：

```text
PSKA API          OK
PSKA HTTP MCP     OK
Hermes WebUI      OK
RAGFlow API/Web   OK
GBrain memory     OK
Embedding dev     OK
Eidolia           OK
Graphiti          OFF optional, not selected
```

当前 provider：

```text
retrieval = ragflow
kb        = ragflow
memory    = gbrain
embedding = local_infinity_dev, BAAI/bge-m3
```

## Alpha Readiness 证据

命令：

```bash
curl -fsS http://127.0.0.1:8765/api/alpha/readiness
```

结果摘要：

```text
runtime_diagnostics   pass
provider_configuration pass
workspace_context     pass
kb_gateway            pass
kb_readiness          pass
source_safety         pass
memory_governance     pass
memory_health         pass
review_queue_load     pass
user_trial_ux         pass
```

其中 `user_trial_ux` 的通过条件是能力表中同时存在：

```text
pska_alpha_trial_guide
pska_alpha_recovery_plan
pska_alpha_first_run_session
pska_alpha_first_run_item_update
```

这些能力只提供试用引导、恢复边界说明和操作员进度记录，不会自动执行备份、恢复、源文件写回或真实试用步骤。

## 完整组件闭环证明

使用 ready 的 mock finance dataset：

```text
dataset_id = 07f35e1a9b9411f197ff8391030412c0
name       = pska_full_flow_finance_demo_20260819_140550
```

命令：

```bash
PSKA_COMPONENT_DATASET_IDS=07f35e1a9b9411f197ff8391030412c0 \
PSKA_COMPONENT_QUESTION='Summarize the fictional Northstar Robotics Q2 finance demo with cited evidence and next actions.' \
PSKA_COMPONENT_LIMIT=4 \
PSKA_COMPONENT_RETRIEVAL_LIMIT=2 \
PSKA_COMPONENT_SOURCE_INSPECTION_LIMIT=2 \
PYTHONPATH=src .venv/bin/python -m pska_essential.component_check --env-file .env.pska
```

结果：

```text
status = ok
mode   = full_component_proof

runtime.diagnostics ok
memory.probe        ok
retrieval.probe     ok
closed_loop.probe   ok
```

闭环输出：

```text
run_id                  = run_80ff717b913e405c8f1ed74e67b41f05
memory_count            = 1
retrieval_context_count = 2
closed_loop_contexts    = 4
closed_loop_sources     = 9
source_inspection_count = 2
exported                = true
export_format           = json
```

这证明当前实例可以完成：

```text
ready scope 检查
RAGFlow 检索
GBrain 记忆探针
Agentic Ask
源片段读取
可追溯 JSON 导出
审计记录写入
```

## Hermes WebUI Extension 证据

契约测试：

```bash
HERMES_WEBUI_PASSWORD=****** make webui-extension-contract
```

结果：

```text
total  = 35
passed = 35
failed = 0
```

覆盖：

```text
WebUI login
extension manifest/js/css
sidecar health
workspace status
embedding component
KB datasets
runtime diagnostics
alpha readiness
alpha first-run session/checklist update
Hermes profile/projects/workspaces
RAGFlow probe
memory-only preview
dataset-scoped preview
Jarvis Brief
Agentic Brief
Source Recall
Memory search/review candidate/reject
Kanban projection
Digest task
chat bridge skill dependency
chat bridge forced injection/sanitizer contract
```

视觉测试：

```bash
NODE_PATH=/tmp/pska-playwright/node_modules \
PSKA_PLAYWRIGHT_MODULE=playwright-core \
PSKA_PLAYWRIGHT_CHANNEL=chrome \
HERMES_WEBUI_PASSWORD=****** \
make webui-extension-visual
```

结果：

```text
ok = true
desktop menu visible and in viewport
desktop Source Recall returns visible results
Memory page visible with memory and review data
mobile PSKA chip visible and not overlapping send
mobile menu visible and in viewport
console warnings/errors = 0
```

真实发问链路测试：

```bash
NODE_PATH=/tmp/pska-playwright/node_modules \
PSKA_PLAYWRIGHT_MODULE=playwright-core \
PSKA_PLAYWRIGHT_CHANNEL=chrome \
HERMES_WEBUI_PASSWORD=****** \
make webui-extension-turn-bridge
```

结果：

```text
ok = true
Hermes /api/chat/start intercepted
forced_context_count = 1
message_length = 10417
visible user turn remains clean
```

这证明 `pska-mini` 不是只在面板里展示状态；当用户在 Hermes WebUI 里真实发送问题时，extension 会把 PSKA skill、dataset scope、source root scope 注入到 Hermes 的 `message` 字段，同时聊天窗口仍只显示用户原始问题。

真实 LLM 回答侧 proof：

```bash
NODE_PATH=/tmp/pska-playwright/node_modules \
PSKA_PLAYWRIGHT_MODULE=playwright-core \
PSKA_PLAYWRIGHT_CHANNEL=chrome \
HERMES_WEBUI_PASSWORD=****** \
make webui-extension-llm-proof
```

结果：

```text
ok = true
session_id = da2146f8fc2d
kept_session = false
message_length = 10462
answer_length = 2144
answer_proof_record.status = recorded
proof_id = hproof_0768c2ba9aa24a92b1ba82897b56fc99
audit_event_id = aud_641fa296c6124247b51f3804e3293661
```

回答侧实际完成的 PSKA 工具调用：

```text
mcp__pska_essential__pska_source_root_list
mcp__pska_essential__pska_source_search
mcp__pska_essential__pska_workspace_status
mcp__pska_essential__pska_source_read
mcp__pska_essential__pska_memory_search
```

该 proof 还确认：

```text
LLM stream completed without terminal error
Answer-side turn stayed read-only
write_like_events = 0
Final answer is substantive and source-oriented
Visible user turn remains clean
Temporary WebUI session cleanup OK
Persist Hermes answer proof in PSKA audit OK
```

这条 proof 会真实调用模型，因此不放进默认 `alpha-acceptance-webui`；需要展示 Hermes Agent 确实使用 PSKA 时再显式运行。成功后它会写入 `hermes.answer_proof` audit 事件；可通过 `GET /api/hermes/answer-proofs` 或 `GET /api/trace/query?action=hermes.answer_proof` 反查，保存的是问题/回答预览、哈希、工具调用摘要和检查结果，不保存完整回答文本。

## 记忆治理状态

当前 GBrain Memory Card：

```text
backend    = gbrain
card_count = 10
health     = ok
issues     = 0
```

当前 Review queue：

```text
pending_count                 = 13
accepted_unapplied_count      = 0
candidate_quality_issue_count = 0
```

本轮治理处理了一条低质量候选：

```text
review_id = rev_prop_abd25fba86ca422ca573aa11730a2f65
status    = rejected
reason    = annual-report evidence belongs in KB/RAG, not long-term personal memory
```

这条候选没有写入 GBrain。

## 边界

当前可演示和 dogfood 的能力：

```text
Hermes WebUI extension 作为唯一用户入口
PSKA Product API / HTTP MCP 作为边界
RAGFlow ready dataset 检索和 Ask
GBrain 记忆检索和治理写入路径
Memory Review queue
Agentic Context Brief / Jarvis Brief
Source Recall
Eidolia 相关 source/memory 场景
Alpha trial guide / recovery plan / first-run checklist
```

仍保持锁定或可选的能力：

```text
Graphiti 是 optional，当前不在主链路
native source writeback 需要备份确认
duplicate cleanup 仍是 proposal/review-only，不执行删除/移动/合并
provider backups 和 rollback 需要人工演练
RAGFlow next / Hermes WebUI next 是 side-by-side optional，不影响主线
```

## 验收命令清单

推荐入口：

```bash
make alpha-acceptance ENV_FILE=.env.pska PYTHON=.venv/bin/python
```

演示前完整入口，包含 Hermes WebUI extension 契约和浏览器级视觉 smoke：

```bash
NODE_PATH=/tmp/pska-playwright/node_modules \
PSKA_PLAYWRIGHT_MODULE=playwright-core \
PSKA_PLAYWRIGHT_CHANNEL=chrome \
HERMES_WEBUI_PASSWORD=****** \
make alpha-acceptance-webui ENV_FILE=.env.pska PYTHON=.venv/bin/python
```

这两个入口默认把原始 JSON 证据、`summary.json` 和 `summary.md` 写入 `/tmp/pska-alpha-acceptance-*`，不写入仓库，也不保存密码或 provider token。

拆分命令：

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
HERMES_WEBUI_PASSWORD=****** make webui-extension-contract
NODE_PATH=/tmp/pska-playwright/node_modules \
  PSKA_PLAYWRIGHT_MODULE=playwright-core \
  PSKA_PLAYWRIGHT_CHANNEL=chrome \
  HERMES_WEBUI_PASSWORD=****** \
  make webui-extension-visual
NODE_PATH=/tmp/pska-playwright/node_modules \
  PSKA_PLAYWRIGHT_MODULE=playwright-core \
  PSKA_PLAYWRIGHT_CHANNEL=chrome \
  HERMES_WEBUI_PASSWORD=****** \
  make webui-extension-turn-bridge
NODE_PATH=/tmp/pska-playwright/node_modules \
  PSKA_PLAYWRIGHT_MODULE=playwright-core \
  PSKA_PLAYWRIGHT_CHANNEL=chrome \
  HERMES_WEBUI_PASSWORD=****** \
  make webui-extension-llm-proof
PSKA_COMPONENT_CONNECTIVITY_ONLY=1 \
  PYTHONPATH=src .venv/bin/python -m pska_essential.component_check --env-file .env.pska
```

最近一次结果：

```text
unittest                472 tests OK
webui-extension-contract 35/35 OK
webui-extension-visual   OK
webui-extension-turn-bridge OK
webui-extension-llm-proof optional OK
live-connectivity-check  OK
full-component-proof     OK
```

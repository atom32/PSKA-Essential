# PSKA 当前用户手册

日期：2026-08-20

这份手册只描述当前这台机器上已经能跑通、能演示、能被 API 或 Hermes WebUI extension 触达的能力。PSKA 现在不是一个独立前端产品；它是 Hermes WebUI 背后的知识、来源、记忆、审核和审计控制层。

如果目标是“徐大为作为第一个用户，怎样用 PSKA 辅助自己的日常生活”，先读：

```text
/Users/xudawei/PSKA-Essential/docs/PSKA_FIRST_USER_DOGFOODING_PLAYBOOK.zh.md
```

## 1. 先知道自己在用什么

日常入口是：

```text
Hermes WebUI: http://127.0.0.1:8787
```

PSKA 自己的服务入口是：

```text
PSKA Product API: http://127.0.0.1:8765
PSKA MCP HTTP: http://127.0.0.1:8766/mcp
```

对普通使用者来说，应该从 Hermes WebUI 进入，通过 `pska-mini` 扩展选择资料范围、请求召回、查看记忆和处理审核项。`http://127.0.0.1:8765` 上的本地页面只用于开发诊断，不作为 PSKA 独立工作台。

当前本机完整链路包括：

```text
Hermes WebUI
  -> pska-mini extension
  -> PSKA Product API / PSKA MCP
  -> Source Registry / Review / Audit / Memory Governance
  -> RAGFlow / GBrain / Graphiti / Eidolia
```

各组件的分工：

| 组件 | 作用 | 用户应该怎么理解 |
| --- | --- | --- |
| Hermes WebUI | 日常聊天和操作入口 | 在这里提问、选择范围、看 PSKA 面板 |
| PSKA | 资料、记忆、审核、追踪的控制层 | 不直接替你聊天，而是给智能体提供可信上下文 |
| RAGFlow | 文档知识库 | 保存上传文档、切片、解析、检索 |
| GBrain | 当前接入的长期记忆组件 | 保存通过审核的长期记忆卡 |
| Source Registry | 本地文件夹资料索引 | 管理本机文件夹、搜索、查重、标签、评论 |
| Eidolia | 无限画布创作工作台 | 产出 thought/artifact，PSKA 可以引用和沉淀 |
| Review Queue | 审核收件箱 | 重要记忆、冲突候选、低质量候选先到这里 |
| Audit / Trace | 操作轨迹 | 解释某个来源、记忆、回答为什么出现 |

## 2. 启动和检查

在仓库目录运行：

```bash
cd /Users/xudawei/PSKA-Essential
./scripts/start_pska_workspace.sh --status-only --no-open
```

当前一次实测结果是：

```text
RAGFlow: OK
RAGFlow task executor: OK
GBrain HTTP MCP: OK
Graphiti optional: OFF, not selected
PSKA Product API: OK
PSKA MCP HTTP: OK
Eidolia: OK
Hermes WebUI: OK
```

如果要打开工作区，可以运行：

```bash
cd /Users/xudawei/PSKA-Essential
./scripts/start_pska_workspace.sh
```

然后进入 Hermes WebUI。打开 PSKA 面板后，应该能看到 health/status、dataset 选择、scope 设置、Jarvis Brief、Agentic Brief、Source Recall、Memory/Review 等入口。
进入 PSKA Memory 主页面后，还能看到 alpha readiness、First-run checklist 和 Recent Answer Proofs；清单只记录人工试用进度，不会自动扫描文件、创建备份、写源文件或写长期记忆。

## 3. Hermes WebUI 里的基本操作

`pska-mini` 扩展目前提供：

- composer chip：在输入框附近启用或关闭 PSKA。
- dataset/document scope：选择本轮问题使用哪个知识库和文档范围。
- Source Root IDs：指定本地资料文件夹范围。
- Preview：预览本轮会注入的 PSKA 上下文。
- 真实发问桥接：在 Hermes WebUI 里发送问题时，把已选资料范围带入本轮请求，同时聊天窗口仍只显示用户原始问题。
- Jarvis Brief：查看当前工作区的摘要、问题、待办和建议动作。
- Agentic Brief：让 PSKA 在回答前整理证据、来源、记忆和历史轨迹。
- Source Recall：不用 embedding，按本地文件元数据和全文索引召回资料。
- Memory 页面：搜索长期记忆，创建记忆候选。
- Recent Answer Proofs：查看最近 Hermes 回答实际观测到的 PSKA 工具调用、只读状态和资料范围，并可点开 `View Trace` 看 proof 对应的 trace entries。
- Review 页面：查看候选，接受、拒绝，或把已接受候选写入长期记忆。
- First-run checklist：记录首次 dogfooding/alpha 试用的人工确认状态和备注。
- Kanban 投影：把 PSKA 审核项同步到 Hermes 的 `pska-review` 看板。
- Digest Runner：创建 Hermes Tasks 入口，用于摘要和消化任务。
- LLM proof：可选地让 Hermes 真实回答一次，确认回答侧调用了 PSKA 工具、没有写入型动作，清理临时会话，并把回答侧 proof 写入 PSKA audit。

它现在故意不提供：

- 独立 PSKA 聊天页。
- 独立 Eidolia 页面。
- 独立 Ask 面板。
- 上传 UI。
- 浏览器直连 RAGFlow 或 Graphiti 的管理界面。

这些限制是设计边界。日常对话走 Hermes，PSKA 负责让 Hermes 在回答前拿到可审计的来源、记忆和范围。

## 4. 案例一：把本地文件夹变成可管理资料源

真实演示资料在：

```text
/Users/xudawei/PSKA-Essential/demo/full_flow_mock/source_root
```

里面包含：

- `2026-q2-earnings-digest.md`
- `management-action-ledger.md`
- `risk-and-question-register.md`
- `memory-candidates.md`
- `duplicates/2026-q2-earnings-digest-copy.md`

已注册的资料源是：

```text
Root ID: root_ebdf0044b0442f494246012f
Label: PSKA full-flow mock finance folder writable sidecar
Permission: sidecar_write
Scan: 6 scanned, 6 indexed, 0 errors
Duplicate groups: 1
```

你可以在 Hermes WebUI 的 PSKA 面板里把这个 root id 填到 `Source Root IDs`，然后在聊天框输入：

```text
请从本地财报 mock 文件夹里召回关于收入增长、现金流、库存和未交付订单的资料。
```

点击 `Source Recall`，预期效果是：PSKA 返回本地文件片段、标题、路径和摘要。这个召回优先使用文件索引和全文搜索，不依赖 embedding。

这个案例已经验证过：

- 能扫描本地文件夹。
- 能搜索本地 markdown 文档。
- 能发现 exact hash 重复文件。
- 能把重复组标记为 reviewed。
- 能生成清理建议，但当前是 dry-run，不会删除或移动源文件。
- 能在 `sidecar_write` 权限下写入 PSKA sidecar 标签和评论。
- 当 root 是 `read_only` 时，tag/comment apply 会被拒绝。

适合的真实用途：

- 管理一批研究资料。
- 管理财报、合同、会议纪要、论文笔记。
- 给资料打标签或评论。
- 找重复文件。
- 在智能体回答前先召回本地证据。

## 5. 案例二：用 RAGFlow 跑知识库问答

真实演示数据集：

```text
Dataset ID: 07f35e1a9b9411f197ff8391030412c0
Name: pska_full_flow_finance_demo_20260819_140550
Parsed chunks: 6
```

演示问题可以这样问：

```text
请基于当前财报 mock 知识库，给出硬件加服务型公司的经营质量分析。
请分成事实、推断、下一步动作，并列出来源。
```

这条链路已经跑通过：

```text
上传文档
  -> 等待 RAGFlow 解析
  -> 如果未解析完成，PSKA 返回 blocked/resume
  -> task executor 启动后 resume
  -> 检索证据
  -> 检查来源
  -> 生成工作产物
  -> 导出
```

真实运行记录：

```text
Blocked run: run_1554d083399c4e1591b2332e7b214a3e
Resumed run: run_8ab43c6c4ca64142be04c864ab6672c9
Proposal: prop_77d72e447f814c189b498d856f9c7a70
Export size: 9265 chars
Context packets: 3
Source inspections: 3
```

这个案例证明：PSKA 不会在 RAGFlow 解析没完成时硬答。如果资料未就绪，它会把任务挂起，并给出可恢复的 run id；解析完成后再继续。

## 6. 案例三：把工作结论变成长期记忆

财报演示中，PSKA 从带来源的工作流里创建了一条记忆审核：

```text
Review: rev_prop_ea713c15b5574a569ed9ed5414efb3ed
Proposal: prop_ea713c15b5574a569ed9ed5414efb3ed
Apply backend: gbrain
GBrain fact: 2
```

写入后的记忆大意是：

```text
财报研究时，优先把回答拆成事实、推断和下一步动作；分析硬件加服务型公司时，要同时看收入增长、毛利率、经营现金流、回款天数、库存、未交付订单兑现、服务毛利和软件附加率。
```

后续再问类似财报问题时，PSKA 可以先找出这条长期记忆，再和 RAGFlow 的当前资料一起交给 Hermes。这样它不是只检索文档，也会记得“你通常希望怎么分析”。

这条链路的关键规则是：

- 上传文档不会自动写长期记忆。
- 问答产物不会自动写长期记忆。
- 只有通过 Review 并显式 apply 的候选，才会进入 GBrain。
- PSKA 会把 GBrain fact 反查回原始 SourceRef，避免记忆变成无来源的口号。

当前记忆健康检查结果：

```text
card_count: 10
issue_count: 0
```

## 7. 案例四：Eidolia 画布如何进入 PSKA

Eidolia 仍然是创作工作台，不是 PSKA 前端。PSKA 通过 SourceRef 引用 Eidolia 的 thought/artifact。

真实演示：

```text
Project: eidolia-demo-northstar-report
Node: thought_fact_inference_action_frame
Source adapter: eidolia
Node type: thought
Review: rev_prop_4d3f7394a9b84e8a8500bbec82cdb5ad
Apply backend: gbrain
GBrain fact: 3
```

写入后的记忆大意是：

```text
Eidolia 财报创作画布中，北星报告采用“事实、推断、行动”三段式。
```

用户侧可以这样使用：

1. 在 Eidolia 里写 thought 或整理 artifact。
2. 让 Hermes/PSKA 引用当前画布节点。
3. PSKA 把节点包装成 SourceRef。
4. 如果这个 thought 值得长期保留，就创建 Memory Review。
5. 人确认后 apply 到 GBrain。

适合场景：

- 基于财报写研究报告。
- 基于人物设定续写小说。
- 把画布上的阶段性结论沉淀成长期创作偏好。
- 保留“当时为什么这样写”的证据链。

## 8. 案例五：继承 ChatGPT 的个性化记忆摘要

目前已导入的是 ChatGPT 的记忆摘要，不是完整对话记录。导入包在：

```text
/Users/xudawei/PSKA-Essential/.pska-essential/imports/chatgpt-memory-seed-2026-08-20
```

里面有：

```text
chatgpt_memory_seed.zh.md
candidate_cards.zh.json
IMPORT_REPORT.zh.md
```

已注册资料源：

```text
Root ID: root_4ecc3ce4ab92fe795b23305c
Label: ChatGPT Memory Seed 2026-08-20
Permission: read_only
Scan: 3 scanned, 3 indexed, 0 errors
```

这批摘要最终形成 8 条已批准并写入 GBrain 的记忆卡：

| Fact ID | 类型 | 范围 | 内容 |
| --- | --- | --- | --- |
| 4 | project_state | project | PSKA 的个人外脑和认知连续性目标 |
| 5 | exclusion | global | 私密人生回忆的保护边界 |
| 6 | identity | global | 用户的职业身份与 AI/知识图谱/NLP 背景 |
| 7 | project_state | workspace | 天大智图公司上下文 |
| 8 | project_state | workspace | 公司产品线 |
| 9 | working_habit | workspace | PSKA/Hermes/Eidolia/GBrain 等系统栈偏好 |
| 10 | preference | project | 创作项目和叙事母题偏好 |
| 11 | project_state | workspace | 适合 dogfooding 的真实领域 |

最重要的是 fact `5`：私密人生回忆不应默认拆成普通长期行为记忆，也不应在无关任务中主动暴露具体人物和亲密细节。它是保护边界，不是八卦索引。

目前的状态：

- ChatGPT 记忆摘要已经进入 Source Archive。
- 候选卡已经过 Review。
- fact `4` 到 `11` 都已写入 GBrain。
- 每条都能追溯到 `chatgpt_memory_seed.zh.md`。
- 完整 ChatGPT 对话记录还没导入。

等完整对话记录导出后，下一步不是直接灌进记忆，而是：

```text
完整对话归档
  -> 注册为 read_only source root
  -> 扫描和索引
  -> 按项目、人物、时间、主题提取候选
  -> 去重和质量检查
  -> Review Queue
  -> 人确认后 apply
```

## 9. 记忆卡怎么用

PSKA 当前把长期记忆当作 Memory Card 来治理。一个合格记忆卡至少应该有：

- 记忆文本：这件事是什么。
- 记忆类型：身份、偏好、项目状态、工作习惯、排除规则等。
- 作用范围：全局、工作区、项目。
- 行为影响：以后系统应该怎么改变回答方式。
- 来源引用：这条记忆从哪里来。
- 生命周期：何时创建、何时修改、是否被替代。

在 Hermes WebUI 的 PSKA Memory 页面可以：

- 搜索长期记忆。
- 查看记忆的来源数量。
- 创建新的记忆候选。
- 把候选送入 Review。

在 Review 页面可以：

- 查看 pending 候选。
- 接受、拒绝或修改。
- 对 accepted 但未 apply 的记忆执行 apply。

当前已有 10 条 active 记忆卡，其中：

```text
fact 2: 财报研究工作习惯
fact 3: Eidolia 财报创作画布方法
fact 4-11: ChatGPT 记忆摘要导入后的第一批长期记忆
```

## 10. 什么时候不要写记忆

这些内容不建议直接变成长期记忆：

- 一次性情绪宣泄。
- 还没确认的猜测。
- 太空泛的总结，例如“用户很重视知识管理”。
- 没有行为影响的描述。
- 私密关系和家庭细节，除非用户明确要求整理自传或创作素材。
- 模型推断出来的人格判断。

更好的做法是：

```text
原文进入 Source Archive
  -> 只提炼必要候选
  -> 私密内容加保护边界
  -> 让用户确认
  -> 再写长期记忆
```

这也是为什么 ChatGPT 记忆摘要导入时，PSKA 没有把所有人生回忆拆成几十条永久记忆，而是先建立了保护边界。

## 11. 资料查询和记忆查询的区别

资料查询回答的是：

```text
文件里有什么？
```

记忆查询回答的是：

```text
我长期应该记住什么？
```

Agentic Brief 则回答：

```text
Hermes 在这次回答前，应该先看到哪些证据、来源、记忆和历史轨迹？
```

真实演示中生成过：

```text
Brief: agentic_brief_7b69a0fdd4af48368e000ce3270a4272
Status: ready
KB evidence blocks: 4
Local source recall: 4
Relevant memories: 2
Trace signals: 9
Next actions: 8
```

它的用途不是替 Hermes 回答，而是在 Hermes 回答前整理上下文，降低“凭空答”的概率。

## 12. 一个完整使用流程

以“基于财报写一份经营分析报告”为例：

1. 把财报、会议纪要、风险清单放入本地文件夹。
2. 在 PSKA 注册这个文件夹，权限先用 `read_only`。
3. 扫描文件夹，确认文件数量和错误数。
4. 用 Source Recall 搜“收入增长、现金流、库存、订单”。
5. 如果需要知识库问答，把文件送入 RAGFlow dataset。
6. 等 RAGFlow 解析完成。
7. 在 Hermes WebUI 选择 dataset 和 source root。
8. 输入问题：要求分事实、推断、下一步动作，并列来源。
9. PSKA 生成 Agentic Brief，把证据、来源、记忆和 trace 交给 Hermes。
10. Hermes 写出报告草稿。
11. 把报告中值得长期保留的分析习惯或项目结论创建为 Memory Review。
12. 人确认后 apply 到 GBrain。
13. 后续再写同类报告时，PSKA 会同时召回当前资料和历史分析习惯。

这个流程里的关键点是：文件还是文件，知识库还是知识库，记忆只是经过审核后的长期投影。PSKA 的价值就在于不把它们混成一锅。

## 13. 当前能演示什么

当前已经可以演示：

- Hermes WebUI 作为主入口。
- PSKA extension 选择范围和预览上下文。
- Hermes WebUI 真实发送问题时，PSKA 范围会进入本轮请求，且不会污染可见聊天记录。
- 本地文件夹扫描、索引、召回。
- 本地文件夹查重。
- 只写 sidecar 的标签和评论。
- RAGFlow dataset 上传、解析、检索、blocked/resume。
- 有来源的工作产物导出。
- 从工作流创建长期记忆候选。
- Review 接受后写入 GBrain。
- GBrain fact 回查 PSKA 来源引用。
- ChatGPT 记忆摘要导入成 Memory Card。
- 私密记忆保护边界。
- Eidolia thought 通过 SourceRef 接入 PSKA。
- Agentic Context Brief 汇总证据、来源、记忆和 trace。
- Memory health 检查。
- Review Queue 查看候选质量、重复候选和待处理项。
- Recent Answer Proofs 在 Hermes extension 主页面展示最近回答侧工具调用 proof，并支持点开查看 trace、checks 和完成的 PSKA 工具。
- Alpha readiness 与 First-run checklist 可在 Hermes extension 主页面查看和更新。
- Hermes Kanban `pska-review` 投影。
- Hermes Tasks `PSKA Digest Runner` 入口。
- 可选真实 LLM proof：Hermes 回答侧调用 PSKA source root list、source search、workspace status、source read 和 memory search，并保持只读；proof 会落到 `hermes.answer_proof` audit，可用 `/api/hermes/answer-proofs` 或 `/api/trace/query?action=hermes.answer_proof` 反查。

当前还不应该承诺：

- 面向普通用户的独立 PSKA 前端。
- 完整 ChatGPT 对话记录已经导入。
- 任意文件格式都能完美解析。
- 全自动整理私人硬盘且自动删除重复文件。
- Agent 可以绕过 Review 直接写长期记忆。
- PSKA 已经成熟到无需人工确认的个人全息外脑。

## 14. 常见问题

### 为什么上传文件后没有立刻能问？

RAGFlow 需要解析、切片和建立索引。PSKA 会检查 readiness。如果没准备好，它会返回 blocked/resume，而不是编造答案。

### 为什么 memory.source_federation 显示 skipped？

有时 RAGFlow 普通检索已经拿到了同一批 chunk，PSKA 去重后不会重复读取。这不等于来源丢失。

### 为什么要 Review？

因为长期记忆会改变未来回答方式。PSKA 的原则是：资料可以先归档，记忆必须被治理。

### GBrain 发挥作用了吗？

发挥了。当前 fact `2`、`3`、`4` 到 `11` 都已在 GBrain 中成为 active 记忆，并且 PSKA 能补回来源和记忆卡结构。

### Graphiti 和 GBrain 都是什么关系？

它们都是可替换或可组合的记忆/图组件。当前主路径使用 GBrain 保存长期记忆；Graphiti 是可选图记忆 provider，只有在专门验证图记忆时才需要常驻。PSKA 不把自己绑定死在某个 provider 上，而是要求它们通过 Memory Card、SourceRef、Review、Audit 这些合同接入。

### Eidolia 是不是 PSKA 的一部分？

不是独立前端意义上的一部分。它是创作工作台。PSKA 可以引用它的 thought/artifact，并把其中值得长期保留的内容转成有来源的记忆候选。

### 接下来导入完整 ChatGPT 对话要怎么做？

先把导出的对话文件作为只读资料源注册和索引。然后按项目、时间、人物、主题提取候选卡。候选要去重、检查质量、进入 Review。只有确认后的内容才写入长期记忆。

## 15. 命令速查

检查服务：

```bash
cd /Users/xudawei/PSKA-Essential
./scripts/start_pska_workspace.sh --status-only --no-open
```

查看记忆健康：

```bash
curl -sS 'http://127.0.0.1:8765/api/memory/health?limit=30' | jq
```

查看 active 记忆卡：

```bash
curl -sS 'http://127.0.0.1:8765/api/memory/cards?limit=20&status=active' | jq
```

查看 Review Queue：

```bash
curl -sS 'http://127.0.0.1:8765/api/memory/review-queue' | jq
```

查看资料源：

```bash
curl -sS 'http://127.0.0.1:8765/api/sources/roots' | jq
```

本机真实案例报告：

```text
/Users/xudawei/PSKA-Essential/demo/full_flow_mock/RUN_REPORT.zh.md
/Users/xudawei/PSKA-Essential/.pska-essential/imports/chatgpt-memory-seed-2026-08-20/IMPORT_REPORT.zh.md
```

## 16. 本手册核验记录

写作本手册时，已用当前本机服务复核：

```text
服务状态：RAGFlow、RAGFlow task executor、GBrain HTTP MCP、PSKA Product API、PSKA MCP HTTP、Eidolia、Hermes WebUI 均为 OK；Graphiti 作为 optional provider 当前 OFF 且未被选择，不是 dogfood 主路径必需组件。
本地 Source Recall：对 root_ebdf0044b0442f494246012f 查询“收入增长、现金流、库存、未交付订单”，返回 3 条命中。
RAGFlow dataset：07f35e1a9b9411f197ff8391030412c0 可列出，document_count=4，chunk_count=6。
Memory health：card_count=10，issue_count=0。
Memory cards：active fact id 为 2 到 11，均带 source_refs。
Agentic Brief：新建核验 brief 成功，状态 ready，召回本地来源 2 条、长期记忆 2 条、trace signal 9 条。
```

RAGFlow 端到端 Ask/export 的证明锚点仍以
`/Users/xudawei/PSKA-Essential/demo/full_flow_mock/RUN_REPORT.zh.md`
为准；这份报告记录了 upload、readiness、blocked/resume、source recall、export、Memory Review、GBrain apply、Eidolia bridge 和 Agentic Context Brief 的完整链路。

## 17. 一句话总结

PSKA 当前已经不是只有胶水层的想法：它可以把本地文件、RAGFlow 知识库、Eidolia 画布、ChatGPT 记忆摘要和 GBrain 长期记忆接在一起，并用来源、审核、记忆卡和审计轨迹约束智能体。但它还处在可演示和可 dogfooding 阶段，离面向普通用户的稳定产品还有距离。

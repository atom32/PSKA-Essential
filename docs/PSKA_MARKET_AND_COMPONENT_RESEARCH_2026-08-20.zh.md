# PSKA 对位方案与可吸纳组件研究

日期：2026-08-20

## 1. 结论

本轮调研的结论很直接：

> 市面上没有一个方案完整对位 PSKA。
>
> 但市面上已经有很多成熟组件，分别覆盖了 PSKA 的一部分能力。

PSKA 不应该把自己做成另一个 RAGFlow、NotebookLM、Mem0、Zep、Letta、Khoj、Paperless 或
Heptabase。更合理的定位是：

```text
PSKA = 个人外部认知系统的治理控制层

它负责：
SourceRef
Memory Card
Review Gate
Policy
Audit
Trace
provider adapter
跨对话、跨工具、跨画布的记忆与证据一致性
```

外部组件可以非常强，但进入 PSKA 后必须服从 PSKA 的治理合约：

```text
external tool / memory / RAG / file system / canvas
  -> SourceRef
  -> candidate / proposal
  -> review
  -> governed memory / trace / action
```

这也是 PSKA 相对现有方案的差异：

| 市面方案通常强调 | PSKA 应强调 |
| --- | --- |
| 让 AI 记住更多 | 让“记住”变成有证据、有作用域、有生命周期、有审计的行为 |
| 把资料塞进知识库 | 保持 source of truth，不把来源吞进黑盒 |
| 提升问答命中率 | 同时回答“依据是什么、什么时候知道、后来有没有被推翻” |
| 给 Agent 加 memory | 控制 Agent 能写什么 memory、何时写、谁批准、如何撤回 |
| 做一个独立知识管理前端 | 接入 Hermes WebUI extension 和 Eidolia，不另立 PSKA 前端 |

所以，PSKA 的市场定位不是“最好的 RAG”或“最好的 Agent Memory”，而是：

> 面向个人和小型高认知工作流的外部认知治理层。

## 2. 对位 PSKA 的判断标准

一个方案是否真正对位 PSKA，不能只看它有没有“记忆”或“RAG”。我建议用下面十个维度判断：

| 维度 | PSKA 需要什么 |
| --- | --- |
| 个人长期记忆 | 能保存偏好、经历、判断、知识、项目边界和自我修正 |
| 来源约束 | 每条重要记忆或回答可以追到文件、对话、画布节点或外部证据 |
| 写入治理 | Agent 不能偷偷把推断写成事实，长期记忆需要 proposal/review |
| 时间结构 | 能处理“当时相信什么”“后来被什么替代”“何时过期” |
| 多种检索 | metadata/BM25/hash/link/embedding/graph/temporal retrieval 并存 |
| 文件治理 | 管理用户给定文件夹，支持查询、去重、标签、comment、sidecar |
| Agent 接口 | Hermes 或未来 Agent Runtime 可以用标准工具访问，不绕过 policy |
| 画布创作 | Eidolia 的 thought/artifact 可以变成证据、草稿、记忆候选和 trace |
| 本地与可携带 | 尽量 local-first，至少可导出，不把个人长期认知锁进云端黑盒 |
| 可解释演进 | 能说明系统为什么推荐更新、删除、合并或召回某条记忆 |

用这个标准看，市面方案基本都只覆盖其中一部分。

## 3. 市场地图

### 3.1 接近“个人外脑”的方案

| 方案 | 覆盖能力 | 与 PSKA 的距离 | PSKA 可吸纳方式 |
| --- | --- | --- | --- |
| Personal.ai | 个人/组织记忆、身份、通信网络上的 Agent 栈 | 接近“个人记忆平台”，但更偏商业云平台和通信网络场景 | 参考其“Memory + Identity”定位，不建议作为本地核心依赖 |
| Khoj | 开源个人 AI、second brain、自然语言搜索 notes/documents | 很接近“个人资料问答 + 第二大脑”，但治理和 memory lifecycle 较弱 | 可作为 dogfooding 体验参考，部分文件/笔记 connector 可参考 |
| NotebookLM | source-grounded 笔记/资料问答体验 | 很强的“给定资料问答”，但不是个人记忆治理层 | 作为 source-grounded UX 标杆，不作为 PSKA 替代 |
| OpenMemory / Mem0 | 面向 AI app 和 MCP 的持久记忆能力 | 很适合作为 MemoryProvider，但默认不是 PSKA 的 review/audit 模型 | 接成可替换记忆后端，写入仍走 PSKA Memory Card |
| GBrain | Git/Markdown brain repo、PGLite/Postgres、MCP memory verbs | 作为长期 brain substrate 很强，但不是 PSKA policy/control plane | 放进 `PSKA-Components/gbrain`，作为可选 BrainPort |

判断：

Personal.ai 和 Khoj 最像“普通用户能理解的个人外脑产品”；NotebookLM 最像“用户能立刻感到有用的资料问答产品”；Mem0/OpenMemory 和 GBrain 更适合作为 PSKA 底层能力，而不是产品边界。

PSKA 的特色不能只停留在“我也能记忆”。它必须回答：

```text
这条记忆从哪来？
它为什么值得长期保存？
它只在哪个项目/身份/场景适用？
谁批准写入？
如果它错了，如何修正和追溯？
它影响了哪些回答和行动？
```

### 3.2 Agent Memory / Graph Memory 组件

| 方案 | 强项 | 可吸纳位置 | 风险 |
| --- | --- | --- | --- |
| Mem0 | 给 AI app 增加持久、自改进记忆，支持开源/自托管和多框架集成 | `MemoryProvider`，适合保存简洁用户偏好、事实、项目记忆 | 不应让 Hermes 直接调用 Mem0 写长期记忆，必须经 Review Gate |
| Zep | 企业级 Agent memory，Context Graph、Context Lake、治理、低延迟 context assembly | `GraphMemoryProvider` 或生产化参考 | 托管平台取向较重，本地个人版需要谨慎评估 |
| Graphiti | 开源 temporal context graph，事实有有效期、provenance episode、增量更新 | `TemporalGraphProvider`，非常适合 belief/decision 的时间结构 | 需要额外图数据库和 schema 设计，不能一上来压进核心路径 |
| Cognee | 从文档到 chunk/entity/concept/ontology，再 remember/improve/recall | `MemoryIngestionProvider` 或结构化抽取 pipeline | 容易和 PSKA 自己的 memory envelope 混淆，需只做候选生成 |
| LangGraph/LangMem | 短期/长期记忆、语义/情节/程序性记忆的工程模式 | 设计参考，或作为未来 Agent workflow runtime 的记忆范式 | 更偏 framework pattern，不是完整外脑产品 |
| Letta | Stateful agents、memory system、skills、agent harness | Hermes 替代候选或未来 runtime 对比对象 | 如果直接替代 Hermes，需要单独评估 WebUI、MCP、权限和现有集成 |

最值得吸纳的是 Graphiti/Zep 的时间图谱思想。

PSKA 之前讨论过 Belief And Decision Ledger。它不一定要做成一个独立大系统，更合理的实现是：

```text
Memory Card + SourceRef + Trace + temporal graph projection
```

Graphiti 的 episode/provenance/validity window 和 PSKA 的 SourceRef/Audit 很匹配。它可以让系统区分：

```text
当时相信的事实
后来证实的事实
被替代的判断
仍然有效的项目约束
AI 推断但未确认的内容
```

### 3.3 RAG / 知识库 / 文档问答

| 方案 | 强项 | 与 PSKA 的关系 |
| --- | --- | --- |
| RAGFlow | 深度文档理解、chunking、grounded citations、RAG workflow、agent templates | 当前已经运行，适合作为重要 RetrievalProvider |
| Dify | Knowledge base、workflow、agent 编排、产品化成熟 | 参考 workflow/知识库 UX，不建议替代 PSKA 控制面 |
| AnythingLLM | 本地/团队知识库、文档聊天、Agent、模型连接 | 参考轻量 self-host 用户体验 |
| Open WebUI | RAG/Knowledge、chat UI、模型管理、用户入口 | Hermes WebUI extension 需要避免重复其已有功能 |
| Khoj | 个人 notes/documents 自然语言检索 | 参考 second brain 的用户路径 |
| NotebookLM | 以 sources 为中心的问答、笔记、摘要体验 | 参考“资料先行”的交互，而不是后端架构 |

这些方案多数解决：

```text
资料 -> 检索 -> 摘要/问答
```

但 PSKA 要解决的是：

```text
资料/对话/画布/记忆/Agent 行动
  -> 统一 SourceRef
  -> 证据与记忆治理
  -> 可审计上下文组装
  -> Hermes 使用
  -> 用户批准或撤回
```

因此 RAGFlow 可以很强，但它在 PSKA 中应当是 RetrievalProvider，而不是 PSKA 的大脑。

### 3.4 文件治理与资料管理

| 方案 | 强项 | PSKA 可学习内容 |
| --- | --- | --- |
| Paperless-ngx | 文档管理、OCR、可搜索归档、标签/元数据、Docker 部署 | 文件夹治理、文档 metadata、tag/correspondent/storage path 的成熟模式 |
| DEVONthink | 长期文档库、智能分组、相似文档发现、OCR、Apple 生态体验 | 本地资料库和“帮用户整理”的产品感 |
| Obsidian Omnisearch | 本地 vault 全文搜索 | no-embedding-first 的第一阶段能力参考 |
| Obsidian Smart Connections | vault 语义连接与相似笔记 | embedding 作为可选增强，不作为第一前提 |
| fclones / czkawka / rdfind 类工具 | 文件去重、相似文件发现 | `FileGovernanceProvider` 的底层工具候选 |

PSKA 面向 To C 用户时，一个真实场景是：

```text
用户给几个文件夹：
  ~/Documents
  ~/Downloads
  ~/Desktop/项目材料
  Obsidian vault
  NAS 同步目录

PSKA 要做：
  查询
  source recall
  exact duplicate
  near duplicate
  标签建议
  comment/sidecar
  MOC/索引建议
  “这个文件为什么重要”的记忆化
```

这部分不需要一开始就做成庞大 DMS。更好的路径是：

```text
只读 scan
  -> metadata index
  -> hash / fts / links
  -> reviewable proposal
  -> sidecar/tag/comment apply
```

也就是说，Paperless-ngx 是“文档管理系统”参考；PSKA 是“文件夹作为认知来源”的治理层。

### 3.5 画布、知识图谱笔记与创作空间

| 方案 | 强项 | 与 Eidolia/PSKA 的关系 |
| --- | --- | --- |
| Heptabase | 白板式 visual knowledge management | Eidolia 的知识卡片和空间组织参考 |
| Tana | Supertags、结构化笔记、AI-native workspace | 标签/结构化属性参考，不建议复制其复杂本体 |
| Miro AI / Miro MCP | 团队画布、AI 和 MCP 接入 | 多人画布/Agent 操作画布的参考 |
| tldraw / tldraw computer | AI 操作无限画布、可视化应用原型 | Eidolia 可借鉴 agentic canvas action，但不要改变 thought/artifact 模型 |

这里的边界尤其重要：

```text
Eidolia = 创作工作面
PSKA = 证据、记忆、trace 治理
Hermes = 推理和行动
```

Eidolia 已经有足够好的最小节点模型：

```text
thought
artifact
```

PSKA 不应该把 Eidolia 变成复杂知识图谱前端，也不应该另立一个 PSKA 画布。正确做法是：

```text
Eidolia thought/artifact
  -> PSKA SourceRef(adapter="eidolia")
  -> memory/review/trace candidate
  -> Hermes synthesis
  -> 回写 Eidolia artifact 或 proposal
```

这可以支撑真实演示：

```text
基于财报写报告
基于小说设定续写
把 thought 提升为长期项目记忆
把 artifact 作为可引用证据
查看某个节点背后的来源和 Agent trace
```

### 3.6 平台内置记忆

ChatGPT、Claude 等平台都在增强记忆、项目知识、跨对话上下文。它们很重要，因为它们定义了用户期待：

```text
AI 应该记得我是谁
AI 应该跨对话理解我的项目
AI 应该能管理资料和偏好
AI 应该能删除或修改错误记忆
```

但平台内置记忆的问题也正是 PSKA 的机会：

| 平台内置记忆的问题 | PSKA 的对应设计 |
| --- | --- |
| 记忆摘要容量有限 | Memory Card + source-backed storage |
| “我是谁”的推断不透明 | fact / memory / inference / persona model 分层 |
| 用户难以审计记忆来源 | SourceRef + Audit |
| 跨工具不可携带 | local-first provider adapters |
| 写入策略不完全可控 | Review Gate + policy |

所以 PSKA 不应追求“比 ChatGPT 更会聊天”。它应该让 ChatGPT/Hermes/未来 Agent 都能接入一个更可信的个人认知底座。

## 4. 覆盖矩阵

| 类别 | 代表方案 | 个人记忆 | 来源证据 | 文件治理 | 时间结构 | 画布创作 | Agent Runtime | PSKA 判断 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 个人外脑产品 | Personal.ai, Khoj | 强 | 中 | 中 | 中 | 弱 | 中 | 参考定位和 UX |
| Source-grounded QA | NotebookLM | 弱 | 强 | 中 | 弱 | 弱 | 弱 | 参考用户体验 |
| Agent memory | Mem0, OpenMemory | 强 | 中 | 弱 | 中 | 弱 | 中 | 适合做 MemoryProvider |
| Temporal graph memory | Zep, Graphiti | 强 | 强 | 弱 | 强 | 弱 | 中 | 适合做 TemporalGraphProvider |
| AI memory ingestion | Cognee | 中 | 中 | 中 | 中 | 弱 | 中 | 适合做候选抽取 pipeline |
| 文档 RAG | RAGFlow, Dify, AnythingLLM, Open WebUI | 中 | 强 | 中 | 弱 | 弱 | 中 | 适合做 RetrievalProvider 或参考 |
| 文件管理 | Paperless-ngx, DEVONthink | 弱 | 强 | 强 | 中 | 弱 | 弱 | 适合做 FileGovernance 参考 |
| 画布/PKM | Heptabase, Tana, Miro, tldraw | 中 | 中 | 弱 | 中 | 强 | 中 | 适合 Eidolia 参考 |
| Stateful agent runtime | Letta, LangGraph | 中 | 中 | 弱 | 中 | 弱 | 强 | 适合 Hermes 替代候选研究 |

如果只看单项能力，PSKA 不会赢每个成熟项目。

但如果看下面这个组合能力：

```text
source-backed personal memory
+ governed memory write
+ cross-dialog update
+ file/canvas/source trace
+ multiple retrieval providers
+ Hermes WebUI extension as daily entry
+ Eidolia creative trace
+ optional local brain substrate
```

市面上目前没有一个完整替代品。

## 5. 建议吸纳的组件边界

### 5.1 MemoryProvider

候选：

```text
Mem0 / OpenMemory
Zep
Graphiti
Cognee
GBrain
```

接口建议：

```text
search_memory(query, scope, filters) -> MemoryHit[]
propose_memory(input, source_refs, scope) -> MemoryCandidate[]
apply_memory(review_id) -> MemoryWriteResult
supersede_memory(memory_id, reason, source_refs) -> MemoryWriteResult
delete_or_archive(memory_id, policy) -> MemoryWriteResult
```

关键约束：

```text
provider 可以召回和生成候选
provider 不能直接决定“这就是徐大为的长期记忆”
长期记忆的事实层、偏好层、推断层、人格模型层必须分开
```

### 5.2 BrainPort

候选：

```text
GBrain
未来可能的 OB1/OpenBrain 类项目
Git/Markdown brain repo
PGLite/Postgres/pgvector
```

定位：

```text
BrainPort = 长期 brain substrate adapter
PSKA = brain substrate 的治理者
```

GBrain 如果比 PSKA 自己做得更成熟，就应该吸纳进 `PSKA-Components/gbrain`，但只作为可替换组件。它不应绕过 PSKA Review Gate 直接写入长期认知层。

### 5.3 RetrievalProvider

候选：

```text
RAGFlow
local metadata/BM25/SQLite FTS
Obsidian vault search
Graphiti graph traversal
optional embedding vector store
```

第一阶段仍建议 no-embedding-first：

```text
file path
mtime
hash
frontmatter
markdown links
SQLite FTS/BM25
explicit tags
source route
```

embedding 是增强项，不是地基。理由很现实：

```text
To C 用户给的是几个混乱文件夹
先要知道文件是什么、重复不重复、从哪来、能否引用
语义向量解决不了治理问题
```

### 5.4 FileGovernanceProvider

候选：

```text
Paperless-ngx patterns
Tika / Unstructured / Docling / MinerU
fclones / czkawka
SQLite FTS
sidecar metadata
Obsidian frontmatter/block marker
```

第一版目标：

```text
只读扫描
可解释索引
重复候选
标签/comment proposal
source route 建议
不自动删除、不自动移动、不偷偷改原文件
```

### 5.5 CanvasBridge

候选：

```text
Eidolia current bridge
Miro MCP 作为未来多人/团队画布参考
tldraw AI 作为可视化操作参考
Heptabase/Tana 作为知识空间参考
```

边界：

```text
PSKA 不拥有独立画布
PSKA 不新增 Eidolia 用户可见节点类型
PSKA 只把 thought/artifact 归一化为 SourceRef、memory candidate、trace
```

### 5.6 AgentRuntimeBridge

候选：

```text
Hermes 当前继续作为主入口
Letta 可作为 stateful agent runtime 对比对象
DeepSeek Harness 可在后续作为 Hermes/Hermes WebUI 替代候选研究
Dify/LangGraph 可作为 workflow/runtime 参考
```

PSKA 内部流程不应完全交给 Agent。

更合理的分工是：

```text
Hermes/Agent:
  理解意图
  选择工具
  生成候选
  解释和综合

PSKA deterministic core:
  SourceRef
  policy
  review state machine
  audit log
  memory lifecycle
  provider routing
```

这可以避免“外挂智能”被非确定性 Agent 直接污染。

## 6. PSKA 的产品特色

PSKA 未来对外介绍时，不要只说“个人 RAG”或“AI 记忆”。特色应该这样讲：

### 6.1 可治理的个人长期记忆

不是简单摘要，而是：

```text
这件事我知道
我为什么知道
我什么时候知道
这是事实、偏好、经历、判断还是 AI 推断
它适用于哪个项目
它有没有过期
它是否被新的记忆替代
```

### 6.2 Source-first 外部认知

文件、Obsidian、Eidolia、RAGFlow、对话记录、GBrain 都可以成为来源，但 PSKA 不吞掉它们的事实地位。

```text
source remains source
PSKA governs references, memory, trace, actions
```

### 6.3 跨对话和自动更新

PSKA 的长期价值不是一次问答，而是跨时间：

```text
今天的对话
明天的项目
下个月的修正
几年后的 source recall
几十年后的认知连续性
```

这要求记忆能被更新、替代、撤回和解释。

### 6.4 多种 RAG 并存

PSKA 不押注单一 retrieval 技术：

```text
metadata/BM25/hash/link
embedding
graph
temporal graph
RAGFlow dataset
Eidolia trace
GBrain context pack
```

Hermes 看到的是经过治理的 context，不是 provider 直接吐出来的随机材料。

### 6.5 Eidolia 画布创作闭环

PSKA 的记忆不是只服务聊天，也服务创作：

```text
thought -> evidence
artifact -> draft/report/novel chapter
trace -> why this was generated
review -> what becomes long-term memory
```

这使 PSKA 不只是“问资料”，而是“把长期思考变成可追溯创作”。

### 6.6 Agent 不拥有最终写权

这是 PSKA 的核心安全特色：

```text
Agent 可以建议
PSKA 负责治理
用户拥有批准权
```

这对个人认知系统尤其关键。否则系统会把“AI 认为你是怎样的人”慢慢写回“你是谁”。

## 7. 短期路线

### 7.1 一周内适合做的事

1. 明确 `Provider Adapter Matrix`

   ```text
   MemoryProvider: Mem0/OpenMemory, GBrain, Graphiti candidate
   RetrievalProvider: local FTS, RAGFlow
   FileGovernanceProvider: local scan/hash/sidecar
   CanvasBridge: Eidolia
   AgentRuntimeBridge: Hermes
   ```

2. 做一组对比 benchmark

   输入数据：

   ```text
   ChatGPT 记忆摘要
   未来导出的 ChatGPT conversations
   PSKA docs
   mock personal documents
   Eidolia project trace
   finance report mock case
   novel continuation mock case
   ```

   测试问题：

   ```text
   “我为什么做 PSKA？”
   “这条记忆的证据在哪里？”
   “哪些内容是 AI 推断，不是我确认过的？”
   “这个项目当前该做什么？”
   “哪些文件可能重复？”
   “基于这些财报材料写一份报告草稿。”
   “基于这个设定继续小说。”
   ```

3. 先把 GBrain 接成 BrainPort demo

   目标不是让 GBrain 接管 PSKA，而是证明：

   ```text
   PSKA review -> approved memory -> GBrain remember
   GBrain recall -> PSKA SourceRef/Trace -> Hermes context
   ```

4. 研究 Graphiti 作为 temporal projection

   最小目标：

   ```text
   Memory Card
     -> entity/fact/relation candidate
     -> valid_from / valid_to / supersedes
     -> source episode
   ```

5. 保持 Hermes WebUI extension 为唯一 PSKA 用户入口

   不再新增 PSKA 独立前端。所有可演示能力都应跟进到 Hermes WebUI extension。

### 7.2 暂不建议做的事

| 暂不建议 | 原因 |
| --- | --- |
| 把 PSKA 改成完整 RAG 应用 | 会和 RAGFlow、Open WebUI、Dify、AnythingLLM 重复 |
| 让 Hermes 直接写 GBrain/Mem0 | 会绕过 Memory Card 和 Review Gate |
| 让 Eidolia 增加复杂节点本体 | 会破坏 thought/artifact 的简洁设计 |
| 立即替换 Hermes | runtime 替换会牵动 WebUI、MCP、权限和 demo，DeepSeek Harness/Letta 应单独评估 |
| 先做全盘自动整理 | To C 文件治理风险高，应先只读 audit 和 proposal |
| embedding-first | 对混乱个人文件夹而言，metadata/source/hash/link 更基础 |

## 8. 研究来源

本轮主要使用官方站点、官方文档或 GitHub README：

| 方案 | 来源 |
| --- | --- |
| Personal.ai | https://www.personal.ai/ |
| Mem0 | https://docs.mem0.ai/ |
| OpenMemory | https://github.com/mem0ai/mem0 |
| Zep | https://help.getzep.com/ |
| Graphiti | https://github.com/getzep/graphiti |
| Cognee | https://docs.cognee.ai/ |
| Letta | https://docs.letta.com/ |
| LangGraph Memory | https://docs.langchain.com/oss/python/langgraph/add-memory |
| RAGFlow | https://github.com/infiniflow/ragflow |
| Dify Knowledge | https://docs.dify.ai/guides/knowledge-base |
| Khoj | https://docs.khoj.dev/ |
| Open WebUI | https://docs.openwebui.com/ |
| Paperless-ngx | https://github.com/paperless-ngx/paperless-ngx |
| NotebookLM | https://notebooklm.google/ |
| Heptabase | https://heptabase.com/ |
| Tana | https://tana.inc/ |
| Miro MCP | https://miro.com/ |
| tldraw | https://www.tldraw.com/ |
| ChatGPT Memory | https://help.openai.com/en/articles/8590148-memory-faq |
| Claude Projects / Memory | https://support.anthropic.com/ |

## 9. 最终判断

PSKA 的价值不在于重新实现每一个底层能力。

它的价值在于把这些能力组织成一个可信、可审计、可持续演进的个人外部认知系统：

```text
资料不会丢进黑盒
记忆不会悄悄污染人格
Agent 不能绕过治理
画布创作可以回到证据
旧决定可以被恢复
错误判断可以被更新
未来的自己能知道当年的自己为什么这么想
```

从市场角度看，PSKA 的合理打法是：

```text
用成熟组件做底层能力。
用 PSKA 做记忆、证据、权限和 trace 的控制层。
用 Hermes WebUI extension 做日常入口。
用 Eidolia 承载创作过程。
用 GBrain/Graphiti/Mem0/RAGFlow 作为可替换 provider。
```

这条路线比“自己造一个全能外脑 App”轻，也比“完全交给 Agent 自己记忆”稳。


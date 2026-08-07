# PSKA Alpha 产品简报

日期：2026-08-05  
阶段：Componentized Alpha / Demo Baseline

本文面向 CEO、客户演示和内部评审，回答四个问题：系统架构是什么、交付物是什么、平台是什么、核心能力是什么。

## 一句话定位

PSKA 不是新的聊天产品，而是面向 Agent 的知识治理中间件。它把文档检索、证据引用、创作画布、记忆沉淀和人工复核串成一条可审计链路。

```text
用户入口：Hermes-WebUI / Eidolia
        ↓
Agent 执行：Hermes Agent
        ↓
治理胶水层：PSKA-Essential
        ↓
成熟组件：RAGFlow / SQLite Memory / SQLite Review / 后续 Knowledge Graph
```

## 架构

当前 Alpha 采用组件化架构：

| 层级 | 组件 | 职责 |
| --- | --- | --- |
| 主入口 | Hermes-WebUI | 日常对话入口、PSKA chip、会话与任务承载 |
| 创作工作区 | Eidolia | 画布、Thought/Draft 节点、Evidence artifact、撰写流程编排 |
| Agent 执行 | Hermes Agent | 负责 LLM 调用、推理、正文生成和工具执行 |
| 治理中间层 | PSKA-Essential | scope、证据路由、memory/review 协议、provider 抽象 |
| 文档库 | RAGFlow | 文档上传、解析、chunk、embedding、检索 |
| 轻量治理存储 | SQLite Memory / Review | 当前 Alpha 的记忆和审核闭环 |

边界原则：

1. PSKA 不做 chat，不直接拥有生成 LLM。
2. Eidolia 不直接替代 Hermes；Eidolia 负责画布和创作上下文，生成仍走 Hermes。
3. RAGFlow 是文档库和检索后台，不承担记忆治理。
4. Memory 和 Review 是增强能力；Evidence retrieval 必须在没有长期记忆时仍可用。

## 交付物

Alpha 当前可交付的是一套能跑通的 demo system，而不是单个应用：

| 交付物 | 说明 |
| --- | --- |
| 一站式本机运行环境 | Hermes-WebUI、Eidolia、PSKA-Essential、RAGFlow/embedding 接入 |
| WebUI PSKA 问答 | 在 Hermes-WebUI 里通过 chip 选择 scope，询问财报或知识库问题 |
| Eidolia 撰写模板 demo | 1 个综合展示项目 + 8 个分项目，展示 `PSKA 查询 -> Evidence -> Draft/Audit` |
| Evidence artifact | 可被画布节点引用的只读证据，不写 memory，不触发 review |
| Draft artifact | 由 Hermes 生成并沉淀回 Eidolia 的正文节点 |
| Review + Memory Alpha | SQLite 版本的候选记忆、审核队列、批准后记忆沉淀 |
| 运维文档 | Alpha baseline、compose 部署说明、操作手册、系统交互模型 |

当前 Eidolia 撰写模板 demo 以“四类文档生成/审核”为核心演示面：合同、投标文件、
研究报告、运营报告各有一个生成分项目和一个审核分项目。综合项目承担导航和管理层
讲解，分项目承担可运行链路。

## 平台

对外可以讲成一个“Agent Knowledge Governance Platform”：

```text
PSKA Platform =
  Evidence Platform
+ Workflow Canvas
+ Agent Runtime Bridge
+ Memory Governance
+ Review Protocol
+ Provider Abstraction
```

它不是替代 ChatGPT、Claude、Hermes 或 RAGFlow，而是把这些成熟组件变成可治理、可审计、可复用的知识工作流。

## 核心能力

### 1. Evidence-first 问答

用户先选择 scope，再由 PSKA 调 RAGFlow 取证据，Hermes 基于证据回答。重点不是“能问答”，而是“回答能追溯到哪些文档、哪些 chunk、哪些 scope”。

### 2. Evidence 到 Draft 的创作链

Eidolia 中的 Ask PSKA 节点生成 evidence artifact，后续 Thought/Draft 节点把 evidence 作为显式上下文生成正文。这样检索和生成分开，方便人工检查和二次编辑。

### 3. 记忆治理

普通偏好和低风险事实可以进入 lightweight memory；高风险、冲突、不确定信息进入 review。Memory 不是无限自动写入，而是可审计的候选、批准、合并过程。

### 4. Review 协议

Review 是异常收件箱，不是日常聊天 UI。它负责承接需要人工判断的 memory/canon/fact correction 候选。

### 5. Provider 抽象

RAGFlow、SQLite Memory、SQLite Review 只是当前实现。后续可以替换为 GitHub Review、Neo4j、Graphiti、Mem0、Haystack、LlamaIndex 等 provider。

## 下一阶段能力

### 跨画布能力

目标：一个项目中的 evidence、draft、thought 可以被另一个画布引用。

建议协议：

```text
CanvasRef = project_id + canvas_id + node_id + version
```

这让 Eidolia 不只是单项目白板，而是可组合的知识工作区。

### 画布合并

目标：把多个 Eidolia 项目或多个分支画布合并成一个交付文档包。

最小可行能力：

1. 节点版本记录。
2. Draft 节点 diff。
3. Evidence 引用去重。
4. 冲突节点进入 Review。
5. 合并后生成 assembly manifest。

### 生成结果可信度再确认

目标：Draft 生成后，再跑一次 evidence check，而不是只相信生成模型。

建议流程：

```text
Draft
  ↓
Claim extraction
  ↓
Evidence alignment
  ↓
Unsupported claim list
  ↓
Confidence score
  ↓
Review candidate
```

这会成为 PSKA 的关键卖点：不是只生成正文，而是能确认正文里哪些结论有证据，哪些需要人工补材料。

### 知识图谱故事

Knowledge Graph 不应该被讲成“又一个数据库”，而应该讲成 PSKA 的长期结构化记忆层：

```text
RAGFlow 管原文和 chunk
PSKA 管证据链和治理流程
Knowledge Graph 管实体、关系、时间线和冲突
```

适合放进图谱的对象：

- 人、机构、项目、药品、适应症、试验、文档、申报路径。
- 文档之间的引用关系。
- 结论和证据之间的支持关系。
- 不同版本草稿之间的继承关系。
- 事实冲突和人工裁决结果。

这条故事的重点是：RAGFlow 解决“找到材料”，Knowledge Graph 解决“系统长期理解材料之间的关系”。

## Demo 讲法

五分钟演示建议：

1. WebUI 中选择财报知识库，提一个财务问题，展示 scope、证据和答案。
2. Eidolia 中打开 `00 综合展示：可信文档生成与审核 Demo`，说明当前用 9 个项目模拟未来跨画布/画布包画布能力。
3. 进入一个生成分项目，展示 `章节 -> PSKA 查询 -> Evidence -> 草稿 v1 -> 修改意见 -> 草稿 v2 -> 合并正文`。
4. 进入一个审核分项目，展示按 `审核要点与规范.md` 分段查询证据、生成 Finding、合并 Audit Report / Scorecard。
5. 打开 Prompt Inspector，展示本次指令、显式上下文和最终发送给 Hermes 的 query。
6. 说明下一阶段会加入 Draft 可信度复核、知识图谱和真正的跨画布合并。

## 当前限制

- Demo 材料包不是客户真实业务资料，但 Evidence 节点来自真实 PSKA/RAGFlow 检索。
- Graphiti 不是当前稳定主路径。
- Review/Memory 目前是 Alpha 级 SQLite 实现。
- 跨画布、画布合并、生成后可信度复核和知识图谱仍属于下一阶段能力。
- WebUI session 页面可能只展示最终 agent query 的长文本摘要，不适合作为“用户原始要求”的唯一可视化入口；Eidolia 的 Prompt Inspector 和 draft metadata 才是当前可追溯来源。

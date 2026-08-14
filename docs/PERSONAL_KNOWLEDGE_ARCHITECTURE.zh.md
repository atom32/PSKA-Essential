# PSKA Personal Knowledge Architecture

更新时间：2026-08-12

本文把 PSKA 从现有 Alpha 的“RAGFlow + SQLite Memory + Review”扩展为更清楚的
To C 个人知识架构：用户给出若干本地文件夹和 Obsidian vault，Hermes Agent 通过
PSKA 管理、查询、标注、查重和记忆这些材料。

工程契约见 `ADAPTER_CONTRACTS.md` 的 `PersonalSourcePort`。本文定义产品和
体验边界，adapter contract 定义后续实现需要暴露的对象、工具、权限模式和失败规则。

目标不是再造一个 ChatGPT、Obsidian、RAGFlow、Finder 或向量库。目标是让 Hermes
像一个可靠的个人助理一样知道：

- 哪些文件夹是用户授权的个人知识范围；
- 哪些资料在哪里、是什么状态、是否重复、是否值得保留；
- 哪些项目边界、偏好和纠错应该影响下一次回答；
- 什么时候该查文件、什么时候该查记忆、什么时候该请用户确认；
- 每个回答和每次记忆变更能追溯到什么 source。

## Product Decision

PSKA vNext 应增加一个 personal source layer：

```text
Hermes-WebUI / Eidolia / Obsidian
  -> Hermes Agent
  -> PSKA Product API / MCP
    -> Source Registry
    -> Local Folder Retrieval
    -> Obsidian Vault Adapter
    -> RAGFlow Adapter
    -> Memory / Review / Audit
```

这层解决的是个人文件和笔记的 source management，不是新的生成层。

Hermes 仍然是唯一主要 agentic loop 和生成执行层。PSKA 不做 Chat，不拥有 LLM。
PSKA 负责 scope、权限、索引、出处、记忆治理、工具路由和审计。

## User-Facing Objects

第一版必须让用户看见和控制这些对象，而不是只看见抽象 provider：

| 对象 | 用户理解 | PSKA 行为 |
| --- | --- | --- |
| Source Root | 一个授权文件夹或 vault | 只扫描用户选择的根目录，不默认扫全盘 |
| File Card | 一个文件的状态页 | 路径、类型、大小、修改时间、hash、标签、评论、命中片段 |
| Section | Markdown heading、PDF page、文本段落 | 查询和引用的最小可读单位 |
| Tag | 用户或 agent 建议的标签 | 可写入 sidecar、frontmatter 或 Obsidian tag |
| Comment | 对文件/段落的备注 | 默认写 sidecar；Obsidian markdown 可显式写回 |
| Duplicate Group | 一组相同或疑似重复文件 | 只生成报告和建议，删除必须显式确认 |
| Saved Search | 一个可复用查询视图 | 例如“PSKA 架构文档”“待清理 PDF”“最近改过的小说资料” |
| Memory Card | 会影响未来回答的长期记忆 | 必须说明会改变什么行为，并有 source refs |

如果一条记忆不能回答“它会改变下一次回答的什么行为”，就不应该进入 durable
memory。

## Memory Taxonomy

ChatGPT 式记忆研究给 PSKA 的启发是：记忆不应只是事实列表，而应是用户和助理之间
长期协作的行为状态。PSKA 的 memory UI 和 API 应按下面几类展示。

| 类型 | 例子 | 行为影响 |
| --- | --- | --- |
| Identity | 用户主要用中文写产品设计 | 默认语言和上下文 |
| Preference | 用户偏好短结论、再给实现路线 | 回答格式 |
| Project State | PSKA 不做 Chat，Hermes 是主 agent | 不反复推翻已定边界 |
| Working Habit | 设计稿优先放在 docs，交付放 outputs | 文件和交付路径选择 |
| Source Route | 问 PSKA 架构先查 PSKA-Essential/docs 和 Obsidian/PSKA vault | 检索入口选择 |
| Correction | “主力机不是 X，而是 Y” | 覆盖旧事实 |
| Exclusion | 不要记临时财报测试材料 | 避免污染记忆 |

每条 Memory Card 至少需要：

```text
text: 人能读懂的一句话
type: identity | preference | project_state | working_habit | source_route | correction | exclusion
behavior_delta: 它会让 Hermes 下次怎么做得不同
scope: global | workspace | project | folder
source_refs: conversation / file / Obsidian note / RAGFlow chunk
confidence: explicit_user | reviewed | inferred
refresh_rule: persistent | until_project_done | review_after_date | supersede_on_conflict
status: active | superseded | rejected | deleted
```

默认策略：

- 用户明确说“记住”时，可以走 conversation-native auto apply。
- 文件、digest、批处理抽出来的候选默认只进 Review 或建议列表。
- 重复出现但用户没确认的偏好可显示为“建议记忆”，不能静默写入。
- 路由类记忆非常重要，应优先支持，因为它会直接提升检索质量。

### Memory Quality Gate

本设计研究 ChatGPT 的“个性化 / 记忆 / 记忆摘要”，但 PSKA 不把“摘要得像个人档案”
当作成功标准。合格记忆必须能通过下面的门槛：

| 检查项 | 合格 | 不合格 |
| --- | --- | --- |
| 行为差异 | “问 PSKA 架构时先查 `PSKA-Essential/docs` 和 Obsidian 的 PSKA vault” | “用户关心 PSKA” |
| 证据 | 指向一次明确对话、文件、note heading 或审计结果 | 没有 source，只是模型归纳 |
| 作用域 | 只影响某 workspace/project/folder，除非用户明确要求全局 | 全部写成 global |
| 可淘汰 | 有 correction、supersede 或 review-after 规则 | 永久保留临时事实 |
| 可解释 | Hermes 能说明这条记忆为什么改变了本次行动 | 只能作为人物小传展示 |

因此，PSKA 的 memory review UI 不应只显示“记忆摘要”，而应显示：

```text
Card text
Behavior delta
Scope
Evidence refs
Conflict/supersession status
Last used / last confirmed
Suggested action: keep / revise / narrow scope / delete
```

## Memory As Cognitive Continuity

PSKA 的长期记忆不是“用户画像摘要”，也不是把所有材料复制进一个更小的知识库。它要保存
的是个人认知连续性：

```text
我当时知道什么？
我当时为什么这么判断？
这个判断后来有没有被纠正？
下次 Hermes 应该因此怎么帮我少走弯路？
```

这意味着 Memory Card 的核心不是 `text`，而是 `behavior_delta + evidence + lifecycle`。
一条好记忆应该像一张很薄但很硬的卡片：内容短，边界清楚，能被追溯，能被覆盖。

### Four Memory Layers

为了避免把所有东西都写成 durable memory，PSKA 应显式区分四层：

| 层级 | 保存什么 | 保留多久 | 典型操作 |
| --- | --- | --- | --- |
| Session Memory | 当前对话上下文、刚刚说过的约束 | 当前 session | 自动带入，不写 provider |
| Working Memory | 当前项目、画布、brief、source audit 的活跃状态 | workspace/project 生命周期 | 可生成 artifact 或候选记忆 |
| Durable Memory | 会改变未来行为的稳定规则或纠错 | 按 refresh rule | 通过 conversation/review 写入 |
| Inferred Cognitive Model | 从长期轨迹里总结的思维模式 | 可随时重算 | 只能展示为 inference，不直接当作事实写回 |

第一版要做强的是 Durable Memory；Inferred Cognitive Model 只作为未来能力保留，不要一开始
就做“全息人格模型”。否则系统最容易犯的错就是把“AI 觉得用户像什么人”写成“用户就是
什么人”。

### Memory Card Anatomy

推荐把 Memory Card 当作一个 provider-neutral envelope，而不是依赖 Graphiti、SQLite 或
某个云端记忆产品的私有 schema。

```text
memory_id: stable id
text: 给人读的一句话
memory_type: identity | preference | project_state | working_habit | source_route | correction | exclusion
behavior_delta: Hermes 下次应该因此改变的动作
memory_scope: global | workspace | project | folder | conversation
subject_refs: 可选，指向相关 project/person/source/canvas/artifact
source_refs: conversation / file / Obsidian note / RAGFlow chunk / canvas node
confidence: explicit_user | reviewed | inferred_low | inferred_high
status: candidate | active | superseded | rejected | deleted | stale
refresh_rule: persistent | until_project_done | review_after_date | supersede_on_conflict
created_at / updated_at / last_used_at / last_confirmed_at
supersedes / superseded_by
use_count
```

这些字段里最关键的是：

- `behavior_delta`：如果为空，说明它只是摘要，不是记忆。
- `memory_scope`：默认越窄越好，只有用户明确要求才全局。
- `source_refs`：要能带用户回到当时的对话、note、文件或画布节点。
- `status` 和 `supersedes`：旧记忆必须能被替换，而不是在搜索里互相打架。
- `last_used_at`：系统要知道哪些记忆真的在改变行为，哪些只是长期躺着。

这也是 buy/build 边界：SQLite、Graphiti、Zep、Mem0 或任何后续 memory provider 可以负责
存储、图关系、时间线和检索；但 PSKA 必须自己拥有 Memory Card envelope、`SourceRef`、
Review policy、supersession lifecycle 和 agent-facing search view。否则 provider 一换，
“我是谁、我怎么想、我为什么这么判断”的语义边界也会跟着丢。

### Memory Formation Routes

记忆可以从多个入口形成，但每个入口的治理强度不同。

| 入口 | 例子 | 默认处理 |
| --- | --- | --- |
| Explicit Conversation | “这个以后记住” | 可 conversation-native auto apply，并写 audit |
| Correction | “不对，我的主力机不是 X，是 Y” | 搜索目标记忆，生成 update/delete，旧卡 superseded |
| Source Promotion | “以后问这个项目先查这个 vault” | 默认进 Review，除非用户显式确认 |
| Eidolia Thought | 画布上一个 thought 被用户标成长期判断 | 生成候选 Memory Card，带 canvas/source refs |
| Decision Trace | 一次设计选择有备选项、理由和结果 | ledger 视图保留过程，只有稳定结论升格成 memory |
| Digest / Batch | 从文件夹、文档、项目日志里抽取候选 | 只进建议或 Review，绝不静默长期化 |

这样可以保持用户体验轻：日常聊天里的明确记忆不需要天天去 Review；但批量抽取、文件整理、
跨项目推断和隐私风险较高的内容必须进治理层。

### Belief And Decision As Projections

Belief And Decision Ledger 不应该变成另一个巨型数据库。它更适合做成 `Thought + Trace`
的投影视图：

```text
Belief = Thought(role=belief, claim=..., evidence=..., confidence=..., status=...)
Decision = Thought(role=decision, chosen=..., alternatives=..., rejected_options=..., outcome=...)
Ledger = Trace view ordered by time, source, review, correction, outcome
```

只有当 belief 或 decision 会改变未来行为时，才提炼成 Memory Card：

```text
Decision trace:
2026-08-12: PSKA 保持 Hermes-first，不把 PSKA 自己做成 chat agent。

Memory card:
当讨论 PSKA 架构时，默认坚持 Hermes 是主 agent，PSKA 只做 control plane。

Behavior delta:
以后生成架构方案时，不要建议 PSKA-Essential 直接拥有生成 LLM 或成为第二个 Chat。
```

这能避免叠床架屋：Eidolia 继续只有 thought/artifact，PSKA 通过 metadata、trace 和
review 把其中少数内容升格成可调用的长期记忆。

### Memory Retrieval And Use

Hermes 使用记忆时不应该像普通 RAG 那样“搜到什么塞什么”。更合理的是先分工：

| 查询意图 | 优先查什么 | 记忆的角色 |
| --- | --- | --- |
| 问文件事实 | Source Registry / RAGFlow | 提供 source route 和已知纠错，不替代证据 |
| 问项目状态 | project_state memory + handoff + docs + git | 恢复边界和最近路线 |
| 问写作/创作 | working_habit + Eidolia context + source | 保持风格、路径、输出习惯 |
| 问“我当时为什么这么想” | decision trace + source refs + artifacts | 重建过去判断链 |
| 要求记住/忘记/纠正 | memory search + lifecycle | 找目标、更新、supersede 或删除 |

每次调用记忆时，Hermes 应形成一个小的 `memory pack`：

```text
Relevant active cards
Conflicting or superseded cards, if diagnostic mode
Why each card matters for this turn
Which source refs can verify the card
Whether answer should cite source, memory, or both
```

默认回答里不必机械展示所有记忆，但当记忆改变了行动时，系统应该能解释：“我这次先查
PSKA-Essential/docs，是因为有一条 project-scoped source_route memory。”

### Automatic Update Without Silent Identity Rewrite

跨对话自动更新是 PSKA 的特色，但边界要硬：

- 自动带回：项目边界、source route、最近纠错、活跃 artifact。
- 自动建议：重复出现的偏好、从文件夹 audit 得到的组织路线、Eidolia 中反复出现的判断。
- 自动失效：项目完成后的 project_state、被新纠错覆盖的旧事实、长期未使用且来源弱的推断。
- 不能自动写：人格判断、健康/财务/法律等高风险结论、从模型口吻推断出的身份标签。

自动化应该表现为“帮我发现和维护记忆”，而不是“偷偷替我定义我自己”。PSKA 可以说：

```text
我观察到你最近三次 PSKA 架构讨论都强调 Hermes-first。是否把它设为 project_state？
```

但不应该直接写：

```text
用户是一个 Hermes-first 的人。
```

### Memory Maintenance UI

记忆管理界面不应只是一页“关于你”的摘要。第一版可以做成五个视图：

| 视图 | 用途 |
| --- | --- |
| Active Cards | 当前会影响 Hermes 行为的记忆 |
| Suggestions | 候选记忆，按来源和风险分组 |
| Conflicts | 新旧记忆冲突、scope 冲突、source 冲突 |
| Stale Cards | 到期、很久未用、项目结束、弱来源记忆 |
| Why Used | 最近哪些回答用了哪些记忆，以及用了以后改变了什么 |

这会让记忆变成可管理资产，而不是容量有限、不可解释、越来越空泛的一段 personalization
summary。

## No-Embedding RAG Scenario

To C 用户给 PSKA 的通常不是一个整理好的知识库，而是几个现实文件夹：

```text
~/Documents/Projects
~/Downloads/Archive
~/Library/Mobile Documents/iCloud~md~obsidian/Documents/PersonalVault
/Volumes/Backup/old_writing
```

用户想要的任务是：

- 盘点这些文件夹里有什么；
- 搜某个主题、名字、年份、项目；
- 找重复、旧版、空文件、孤儿文件；
- 给文件打标签或写 comment；
- 给 Obsidian vault 添加结构化索引或 MOC；
- 问一个问题时能先找证据，再让 Hermes 综合；
- 把真正稳定的偏好、项目状态、资料路线升格成记忆。
- 当对话里反复出现稳定偏好、决策、工作习惯或纠错时，先生成带
  `behavior_delta` 和消息证据的 Memory Card 候选，而不是自动写入空泛摘要。

因此无 embedding RAG 第一版应是 local-first lexical retrieval：

```text
source root scan
  -> metadata ledger
  -> text extraction
  -> SQLite FTS5 / BM25
  -> query ranking
  -> source read / section read
  -> Hermes synthesis
```

embedding 可以以后作为 cache 增强，但不是第一版前提。

第一版场景拆成四条实际流水线：

| 场景 | 输入 | 输出 | 写入位置 |
| --- | --- | --- | --- |
| 查询 | query + roots | FTS/BM25 hits、section refs、source reads | 不写源文件 |
| 管理 | audit root | duplicate groups、unresolved links、unlinked notes、route candidates | 只写 PSKA audit/job metadata |
| 标注 | selected source refs + tag/comment | proposal -> apply | tag/comment 默认 `.pska/annotations.jsonl`；Obsidian tag 可显式写 frontmatter |
| Obsidian 组织 | selected vault refs | MOC proposal -> PSKA-managed block apply | vault 内目标 Markdown note 的 marker block |

这也是为什么不能一上来就做全量 embedding：用户要的第一批动作是“找到、盘点、去重、
打标签、评论、建索引”，这些都依赖稳定路径、hash、mtime、links、headings 和权限，而
不是语义相似度。

## Source Registry

Source Registry 是 PSKA 对个人知识源的最小持久层。它不保存原文副本，只保存可重建的
metadata、索引文本、出处坐标和用户标注。

建议 SQLite 表：

```text
source_roots
  root_id, label, kind, absolute_path, permission_mode, created_at, last_scan_at

source_objects
  object_id, root_id, path, kind, mime, size, mtime, ctime, content_hash,
  title, status, deleted_at

source_sections
  section_id, object_id, section_type, heading_path, page, line_start, line_end,
  excerpt_hash, title

source_fts
  object_id, section_id, title, body

source_tags
  tag_id, object_id, section_id, name, origin, write_target, status

source_comments
  comment_id, object_id, section_id, body, origin, write_target, status

duplicate_groups
  group_id, method, confidence, action_status

duplicate_members
  group_id, object_id, reason, content_hash, size

saved_searches
  search_id, label, query, filters, sort, scope
```

权限模式：

- `read_only`: 只扫描和查询，不写回源文件。
- `sidecar_write`: 标签和评论写入 `.pska/` 或 sidecar 文件。
- `native_write`: 对 Obsidian markdown/frontmatter/tag 等可显式写回。
- `managed`: 未来可用于用户明确让 PSKA 管理的工作区。

默认必须是 `read_only` 或 `sidecar_write`，不能默认修改用户原文件。

## Obsidian Role

Obsidian 应作为一等 personal knowledge source，而不是 memory provider。

PSKA 应支持：

- 把一个 vault 注册为 `Source Root(kind=obsidian_vault)`；
- 读取 Markdown、frontmatter、tags、links、backlinks、attachments；
- 把 heading 作为 section；
- 把 MOC、index note、project note 识别为路由入口；
- 把一组 note/heading 或搜索 selector 保存为 source collection，作为可复用问答范围；
- 在用户确认后写入 frontmatter tag、PSKA Comment marker block 或 MOC link；
- 把 Obsidian note 引用转换为 PSKA `SourceRef`。

Obsidian 不应承担：

- durable memory governance；
- agentic loop；
- Review queue；
- 跨 provider 出处解析；
- 非 vault 文件夹的全局索引。

好用的 Obsidian 集成不是“让 Hermes 随便改笔记”，而是：

```text
问答前：用 vault 的 links/tags/frontmatter 缩小 scope
问答中：读取命中的 note/heading 或 source collection 作为 evidence
问答后：用户确认时写回 sidecar tag/comment、Obsidian frontmatter tag、PSKA Comment block、MOC 或创建整理 note
记忆中：只保存路由、偏好、项目状态和纠错，不保存整篇 note
```

## External Component Positions

这些组件可进入设计，但位置不同：

| 组件 | 角色 | 是否第一版核心 |
| --- | --- | --- |
| Obsidian | Markdown vault 和知识写作空间 | 是 |
| SQLite FTS5 | 本地 metadata + 全文检索底座 | 是 |
| MarkItDown / Docling | 文件转 Markdown/结构化文本 | 是，择一先接 |
| OCRmyPDF | 扫描 PDF OCR 预处理 | 可选 |
| fclones / Czkawka / dupeGuru / rmlint | 查重报告和清理建议 | 是，先 dry-run |
| TagSpaces | To C 文件标签/评论交互参考 | 参考，不硬依赖 |
| Recoll / Xapian | 成熟桌面搜索参考或后续 adapter | 可选 |
| Paperless-ngx | 扫描件/票据文档柜 | 后续 vertical adapter |
| Zotero | 论文和引用库 | 后续 vertical adapter |
| RAGFlow | 重文档解析、embedding、知识库后台 | 继续保留 |
| Graphiti | 可选 temporal graph memory | 非主路径 |

原则：

- 已经有成熟产品强项的地方，不重做完整 UI。
- PSKA 第一版要掌握自己的 metadata ledger，因为 To C 文件夹管理需要统一的标签、
  评论、查重、saved search 和出处。
- 外部工具只能在用户同意的 source root 和 permission mode 内工作。

## Plugin And MCP Boundary

2026-08-11 对现成插件/MCP/工具的初步判断：

- ChatGPT/Codex 云端插件适合接 Google Drive、Box、SharePoint、Notion、Zotero 这类
  云端资料源，但不能替代本地 folder/vault 的 To C 主路径。
- MCP Roots 和 filesystem server 很适合表达“用户授权的几个 roots”，但不能让
  Hermes 绕过 PSKA 直接任意读写文件。PSKA 仍要拥有 source root、permission mode、
  audit、sidecar、Review 和 `SourceRef` 契约。
- Obsidian Local REST API + MCP、Omnisearch、Smart Connections 等 Obsidian 生态可以
  作为 vault adapter 或体验参考；其中 Omnisearch 的 BM25/文件名/heading 权重尤其适合
  无 embedding 第一版，Smart Connections 更适合作为后续 embedding cache 参考。
- TagSpaces、Recoll、Czkawka/dupeGuru/rmlint 分别对应 To C 标签评论、本地全文搜索和
  查重清理参考。PSKA 要吸收它们的对象模型，而不是把自己变成这些工具的替代 UI。
- MarkItDown、Docling、Apache Tika、Recoll、ripgrep、SQLite FTS5、fclones 等应被看作
  source-layer implementation choices，而不是产品边界本身。
- 真正的产品闭环是：用户授权几个 folders/vaults -> PSKA 建 metadata/FTS/links/hash ->
  Hermes 经 PSKA search/read/audit -> tag/comment/dedup/source-route 进入建议或 Review。

## Hermes Agent Contract

Hermes 是“会做事”的层，但它的行动必须通过 PSKA 工具完成。

Hermes 应获得这些高层工具，而不是直接访问任意文件系统：

```text
pska_source_root_list
pska_source_root_register
pska_source_scan
pska_source_search
pska_source_read
pska_source_neighbors
pska_source_tag_propose
pska_source_tag_apply
pska_source_comment_propose
pska_source_comment_apply
pska_obsidian_moc_propose
pska_obsidian_moc_apply
pska_duplicate_report
pska_saved_search_create
pska_source_audit_run
pska_source_audit_job_enqueue
pska_source_audit_schedule_create
pska_source_audit_job_list
pska_source_audit_job_tick
pska_source_audit_job_run
pska_source_extract_job_enqueue
pska_source_extract_job_list
pska_source_extract_job_run
pska_source_watch_once
pska_jarvis_briefing
pska_agentic_context_brief
pska_source_memory_review_create
pska_eidolia_context_read
pska_eidolia_memory_review_create
pska_memory_card_list
pska_memory_card_get
pska_memory_refresh_review
pska_memory_health_scan
pska_memory_use_trace
pska_memory_why_used
pska_workflow_memory_attribution
pska_workflow_memory_suggestions
pska_memory_change_from_conversation
pska_memory_search
pska_review_*
```

Hermes 的默认行为：

1. 先根据用户意图选 scope：memory、Obsidian vault、本地文件夹、RAGFlow dataset
   或它们的组合。
2. 对宽泛问题、项目状态、写作/决策前置上下文，先调用
   `pska_agentic_context_brief` 取 evidence、source recall、memory 和 trace，再决定是否进入 Ask。
3. 对文件问题先 search/read source，不直接凭记忆回答。
4. 对稳定偏好、项目边界、路由提示，使用 conversation memory。
5. 对文件整理动作先 propose，写标签、写 comment、删除、移动都需要确认或 workspace
   policy 明确允许。
6. 对重复文件只给 duplicate report，删除永远是单独确认动作。
7. 回答时标明来自 source 还是 memory，不能把二者混在一起。

## Jarvis Bar

这里的“cos Jarvis”不是全知全能，而是达到以下体验：

- 用户说“帮我看看 PSKA 现在卡在哪里”，Hermes 会先查项目记忆，再查 docs，
  再查最近 handoff 和 git 状态，而不是问用户“文件在哪里”。
- 当前实现入口：`pska_jarvis_briefing` 聚合 workspace status、source audit、
  memory/review cues 和可执行 `next_actions`，作为 Hermes 的 Jarvis-style dashboard。
- 当前前置上下文入口：`pska_agentic_context_brief` 把 KB evidence、本地 source
  recall、相关 Memory Card、trace signal 和 specialist role hints 合成一份只读 brief。
- 用户说“整理这些文件夹”，系统能生成文件地图、重复组、标签建议、待确认动作。
- 用户说“这个以后别忘”，系统能把它变成带行为影响的 Memory Card。
- 用户说“这不对”，系统能找目标记忆并更新或标记 superseded。
- 用户问一个材料问题，系统能说明答案来自哪几个文件和段落。
- 用户准备写作或决策，系统能把 Obsidian note、本地文件、RAGFlow 文档和长期记忆
  组合成受限上下文。
- 系统不会擅自扫全盘、改原文件、删除重复文件、写 Graphiti 或把临时材料永久记住。

## MVP Sequence

### M0: Design Freeze

- 本文成为 personal knowledge vNext 的架构入口。
- 现有 RAGFlow/SQLite Review/Memory Alpha 不被推翻。
- Obsidian 被确认纳入 source layer，而不是替代 Memory。

### M1: Read-Only Source Registry

- Done: 支持注册本地 folder 和 Obsidian vault。
- Done: 扫描路径、类型、大小、mtime、hash。
- Done: 抽取 Markdown/txt/code 的标题、heading、正文。
- Done: SQLite FTS5 支持关键词/BM25 查询。
- Done: Product API/MCP 返回 `ContextPacket` 和 `SourceRef`。
- Done: Hermes skill 增加 source search/read 使用规则。

### M2: File Discovery And Views

- Done: 支持 duplicate report；当前已实现 exact hash、外部 fclones/Czkawka hash
  report、内置 `size_name_version` 同名/副本/版本/近似大小候选，以及内置
  `text_similarity` indexed-text token Jaccard 候选；内置 `media_metadata`
  支持 image/video/audio 的同媒体类型、规范化文件名、近似大小候选；optional
  `image_phash` 通过 ImageHash/Pillow 支持图片 perceptual hash 候选。
- Done: 支持 duplicate review list/mark；候选组可被标记为 reported、
  keep_reviewing、reviewed、ignored，并记录 review note，但不执行删除/移动/合并。
- Done: 支持 dry-run duplicate cleanup proposal；可为候选组选择 keep item 并生成
  would-archive 清单，但 apply/delete/move/merge 仍不支持。
- Done: 支持 saved search。

### M3: Sidecar Annotations

- Done: 支持 tag/comment 的 propose/apply。
- Done: 默认只写 `.pska/annotations.jsonl` sidecar，不改原文件。
- Done: `read_only` root 可以 propose，但 apply 会被拒绝。
- Pending: Obsidian markdown/frontmatter native write 仍需显式确认和单独实现。

### M4: Source Neighbors

- Done: 支持 `pska_source_neighbors`。
- Done: 对 Markdown/Obsidian note 记录 outgoing links 和 backlinks。
- Done: 支持 same-folder neighbors，便于从一个命中材料扩展到同项目文件。
- Pending: 更丰富的 Obsidian tags/frontmatter/backlink cache。

### M5: Memory Promotion

- Done: 文件查询或整理结果可以生成“建议记忆”。
- Done: Memory Card 使用本文 taxonomy，需要 `memory_type`、`behavior_delta`、`memory_scope`。
- Done: P2-1 已新增 Memory Card inventory/envelope view：`pska_memory_card_list`、
  `pska_memory_card_get`、`GET /api/memory/cards`、`GET /api/memory/cards/{memory_id}`
  和 WebUI “记忆”面板。
- Done: P2-2 已新增 `pska_memory_use_trace`、`pska_memory_why_used`、
  `GET /api/memory/{memory_id}/use-trace` 和 `GET /api/memory/{memory_id}/why-used`；
  当前解释的是 audit-backed candidate retrieval / card inspection，不冒充最终回答因果。
- Done: P2-3 已新增 `pska_memory_health_scan` 与 `GET /api/memory/health`；
  当前扫描 low-quality、stale/refresh 和 conservative active-card conflicts，并进入
  workspace/Jarvis next actions。
- Done: P2-4 已新增回答级 `memory_attribution`/`used_memory_ids` 与
  `memory_suggestions`；Ask/workflow artifact、export JSON、WebUI Ask/Writing、
  Product API 和 MCP 均可读取。归因只声明 PSKA supplied memory context，
  suggestion 只走 Review，不直接写 Memory。
- Done: P2-5 已新增 `pska_memory_timeline` 与
  `GET /api/memory/{memory_id}/timeline`；它把 Memory Card、lifecycle audit、
  use trace 和 SourceRef 派生成一条时间线，不新建第二套 memory store。
- Done: P2-6 已新增 `pska_memory_briefing` 与 `GET /api/memory/briefing`；
  它把 active cards、health issues、recent use traces 和 timeline/why-used
  next actions 合并成 Hermes/Jarvis/WebUI 的记忆注意力摘要，不直接写 Memory。
- Done: P2-7 已新增 `pska_memory_review_queue` 与
  `GET /api/memory/review-queue`；它把 pending/accepted Review records、
  Memory Briefing focus items 和 health issues 分组到 WebUI “记忆维护队列”，只读 triage，
  不 approve/apply/write Memory。
- Done: P2-8 已新增 `pska_memory_candidate_dedup` 与
  `GET /api/memory/candidate-dedup`；它对 Review 里的 durable memory candidates
  做无 embedding 去重提示，使用 normalized text、token overlap、SourceRef fingerprint
  和 behavior_delta fingerprint 分组，并将 duplicate candidates 接入 Memory Review Queue。
- Done: candidate dedup 进一步输出 `related_groups`，用于提示跨 `memory_scope` 的相关候选或
  scope collision；Memory Review Queue 对应暴露 `related_candidates` group。
- Done: source_route 和 project_state 作为优先用例，当前由 `pska_source_memory_review_create` 支持。
- Done: source-derived memory 默认进入 Review，不直接写 memory provider。
- Done: `pska_source_memory_candidates_from_audit` 与
  `POST /api/sources/memory-candidates/from-audit` 可以从 folder/source audit 的
  route candidates 批量生成 governed Memory Card review candidate。
- Done: 批量候选使用 SourceRef、memory_type、memory_scope、behavior_delta 做确定性去重；
  已存在 pending/accepted/needs_edit review 时跳过，不直接写 memory。
- Done: Eidolia thought/artifact 可通过 `pska_eidolia_context_read` 规范成
  `SourceRef(adapter="eidolia")`，并通过 `pska_eidolia_memory_review_create`
  创建 governed Memory Card candidate。
- Done: `pska_conversation_memory_candidates_create` 可从 Hermes 提炼的对话候选创建 pending
  Review，并在 Memory Review Queue / Jarvis briefing 中单独暴露 conversation candidates。
- Done: conversation candidate review ergonomics 已接入；`needs_edit` 的
  memory_patch review 可在 WebUI/API/MCP 中提交修订后的候选文本、memory_type、
  memory_scope 与 behavior_delta，生成新的 pending Review，并保留原证据链与 revision lineage。
- Done: 批量候选审核 UX 已接入；Memory Review Queue 会给 conversation candidates 与
  pending reviews 暴露 group-level accept/reject，底层入口是
  `POST /api/reviews/batch-decision` 与 `pska_review_decide_batch`。批量决策只改变
  Review 状态，不直接写 durable memory。
- Done: 显式候选合并原语已接入；`POST /api/reviews/merge-candidates` 与
  `pska_review_merge_candidates` 可把 duplicate/related candidate review ids 和人工确认的
  merged `memory_candidate` 文本合并成新的 pending Review，保留合并来源 refs，并把仍 pending
  的旧候选标为 needs_edit；它不自动 approve/apply/write memory。
- Done: duplicate/related candidate queue group 已有轻量内联合并编辑器，可在 WebUI 内填写
  合并后的候选文本与 behavior_delta 并创建合并审核；编辑器会展示成员候选的文本、行为变化、
  type/scope/status/review id，避免盲合并。
- Done: 合并 lineage 已进入 Review API record：merged Review 暴露 `merged_from_review_ids`，
  被替换的旧 Review 暴露 `merged_into_review_id`，WebUI Review card 会显示对应 tags。
- Done: Memory Review Queue 会把被 merge 替换的旧候选分入低优先级
  `merged_replacements` 谱系组，并从 duplicate/related candidate dedup 中排除，避免旧
  `needs_edit` 候选继续污染主动待办。
- Done: 普通 revision 也有同样的队列卫生：产生 successor Review 的旧 `needs_edit`
  会进入低优先级 `revised_replacements`，通过 `next_review_id` 追踪，但不再算主动修改待办。
- Done: Memory Review Queue 新增 `candidate_quality` 质量门；pending 或 accepted 但未 apply
  的 memory_patch review 如果缺 `memory_type`、`memory_scope`、`behavior_delta`、source
  evidence，或文本/行为变化过泛，会被提示先 review/edit，而不是直接进入可 apply 待办。
- Done: `pska_memory_apply` 对 memory_patch 使用同一套质量门；conversation/workflow-derived
  memory proposal 会先补保守 Memory Card envelope，再进入 Review/apply。
- Done: Workspace status 也复用质量门；accepted 但低质量的 memory_patch 不再显示为
  `apply_accepted_memory`，而是引导 Hermes/Jarvis 先做 quality review。
- Done: Memory Review Queue/WebUI 已有第一块候选工作台能力：`candidate_quality`
  item 会带候选文本、缺失字段、type/scope/behavior_delta，并可在队列里一键标为
  `needs_edit` 后提交修订 Review；仍不直接写 durable memory。
- Done: Memory Review Queue summary 新增 `candidate_quality_breakdown`，按
  issue type、missing field、status、severity 聚合，并给出 top issue/missing field，供
  Hermes/WebUI 判断先批量修哪类候选。
- Done: `candidate_quality` group 新增批量 edit action：通过
  `pska_review_decide_batch` 将整组质量问题标为 `needs_edit`，不写 memory，也不自动创建修订
  Review。
- Done: active `needs_edit` memory_patch queue item 现在会暴露结构化 `memory_candidate`
  draft 与 inline revision capability；WebUI 可在批量转入 `needs_edit` 后继续在队列内编辑并提交修订
  Review。
- Done: Memory Card refresh-review seed 已接入；`pska_memory_refresh_review` 与
  `POST /api/memory/cards/{memory_id}/refresh-review` 会从现有 durable Memory Card 创建
  pending `memory_update` Review，记录 refresh reason、previous/proposed text 与
  no-text-change refresh request，强制人工复核且不直接写 durable memory。
- Done: Memory Review Queue 已将 existing-card refresh/update Review 单独暴露为
  `refresh_reviews` group，并提供 `refresh_review_count` 与 `review_memory_refresh`；
  Jarvis/WebUI 可优先处理记忆卡刷新复核，但仍不直接写 durable memory。
- Done: WebUI 记忆维护队列已为 `memory_refresh_review` item 增加专门卡片，直接显示
  source memory id、原记忆、刷新提案和 no-text-change 复核类型，方便人工比较后再打开
  Review 决策。
- Done: Alpha readiness gate 已接入；`pska_alpha_readiness` 与
  `GET /api/alpha/readiness` 会只读判断当前实例适合 owner dogfooding、guided technical alpha
  还是仅 demo/dev，并给出 required failures 与 next actions。
- Done: Alpha trial guide 已接入；`pska_alpha_trial_guide` 与
  `GET /api/alpha/trial-guide` 会把 readiness verdict 转成首次试用路线、guardrails、
  phases 与 exit criteria，但不自动扫描、写源文件或 apply durable memory。
- Done: WebUI Home 已展示 Alpha Trial Guide，包含 trial mode、阶段卡、guardrails 和
  next actions；按钮只导航到 Settings/Sources/Ask/Review，不从向导直接执行危险写入。
- Done: Alpha recovery plan 已接入；`pska_alpha_recovery_plan` 与
  `GET /api/alpha/recovery-plan` 会只读列出 PSKA 本地 SQLite 状态、用户 source roots、
  provider-owned KB/memory state、restore drills 和 writeback preflight，并在 WebUI Home
  的 Alpha Trial Guide 内显示备份/写回边界。
- Done: Alpha first-run session 已接入；`pska_alpha_first_run_session`、
  `pska_alpha_first_run_item_update`、`GET /api/alpha/first-run-session` 与
  `POST /api/alpha/first-run-session/items/{item_id}` 会持久化首次试用清单的人工确认进度，
  只写 PSKA checklist/audit state，不自动执行扫描、写回、备份、恢复或 durable memory apply。
- Done: Alpha first-run notes 已接入；WebUI 每个首次试用 item 都能记录人工确认依据、
  异常或复盘备注，仍然只更新 PSKA checklist/audit state，不把备注写回 source 或直接写入
  durable memory。
- Done: `pska_eidolia_project_trace_import` 可只读导入 Eidolia project files / trace sidecars 为
  PSKA SourceRef/audit trace。
- Pending: 更高级的跨项目语义聚类、批量候选编辑/合并的更完整工作台。

### M6: Agentic Routines

- Done: 用户触发的 folder/vault audit 由 `pska_source_audit_run` 支持。
- Done: audit 输出 root summary、exact duplicate preview、unresolved links、
  unlinked Markdown notes、source-route candidates 和结构化 `next_actions`。
- Done: audit 不写源文件、不直接写 memory、不需要 embedding。
- Done: audit 的 source-route `next_action` 已升级为批量创建记忆候选，入口是
  `pska_source_memory_candidates_from_audit`。
- Done: Obsidian frontmatter tag native write 已通过 `pska_source_tag_propose/apply`
  的 `write_target=obsidian_frontmatter` 落地。
- Done: Obsidian markdown comment native write 已通过 `pska_source_comment_propose/apply`
  的 `write_target=obsidian_markdown_comment` 落地，只追加 PSKA Comment marker block。
- Done: Source collections 已通过 `pska_source_collection_create/list/resolve`
  落地，可保存手动 SourceRef 或无 embedding search selector，并展开为 ContextPacket。
- Done: FTS ranking/snippet 已增强，`pska_source_search` 会输出 `match_reason`、
  `rank_boost`、plain/highlighted snippet，并用 path/title/body LIKE fallback 补 filename route 查询。
- Pending: 项目 handoff 摘要自动化、后台 wakeup 集成。
- 所有写动作仍走 PSKA proposal/review/policy。

### M7: Hermes/Jarvis Briefing

- Done: `pska_jarvis_briefing` 作为 Hermes 的高层工作台入口。
- Done: briefing 合并 workspace status、source roots/source audit、Review/memory cues 和去重后的 `next_actions`。
- Done: 输出 priority codes，如 duplicate、断链、孤立笔记、source route、pending review、workspace action。
- Done: briefing 不生成最终回答、不写源文件、不直接写 memory、不需要 embedding。
- Done: WebUI Home 首屏增加 Jarvis Bar，加载 `/api/jarvis/briefing`，展示 priority、source audit 数字和前三个安全 action。
- Done: WebUI 增加 Sources 面板，支持 root 注册、扫描、资料源 audit、带 ranking/snippet cue 的 FTS 搜索、saved search、source collections、source read、tag/comment proposal -> sidecar apply、Obsidian frontmatter tag apply、Obsidian markdown comment apply，并承接 Jarvis source actions。
- Done: `pska_agentic_context_brief` 与 `/api/agentic/context-brief` 已落地为
  Hermes/WebUI 的 pre-answer context 入口，组合 source recall、memory、trace 和
  next actions，但不生成最终回答、不创建 review、不写源文件、不直接写 memory。
- Done: WebUI Home 增加手动 Agentic Context Brief 控制，按需生成上下文，避免刷新首页时反复启动检索。

### M8: Proactive Source Audit Jobs

- Done: `pska_source_audit_job_enqueue` 把本地 folder/Obsidian scope 记录成 PSKA workflow metadata。
- Done: `pska_source_audit_job_list` 支持按 queued/waiting/running/completed/failed 查看待处理审计。
- Done: `pska_source_audit_job_run` 运行队首或指定 job，复用 M6 的只读 source audit。
- Done: `pska_provider_jobs` 和 workspace status 暴露 queued source audit job，Jarvis/WebUI 可把它显示为可执行 next action。
- Done: Product API 暴露 `/api/sources/audit-jobs`、`/api/sources/audit-jobs/run-next` 和指定 job run 路由。
- Done: job 不写源文件、不直接写 memory、不需要 embedding；source-route 仍必须进入 Review。
- Pending: EXIF/video 级别的媒体近似查重，以及 move/delete/merge proposal 的可执行强确认流程。

### M9: Wall-Clock Source Audit Scheduler

- Done: `pska_source_audit_schedule_create` 创建带 `due_at` 和 cadence 的 waiting source audit job。
- Done: `pska_source_audit_job_tick` 将已到期 waiting job 激活为 queued job；tick 只写 PSKA job metadata，不扫描文件。
- Done: recurring cadence 在 job run 完成后生成下一条 waiting job，并用 `series_id`、`previous_run_id`、`next_run_id` 串联。
- Done: `pska_provider_jobs` 暴露 `due_at`、`due`、`schedule_mode` 和 `activate_due_source_audit_job` next action。
- Done: workspace status/Jarvis action 可以先 tick 到期任务，再运行 queued audit job。
- Done: Product API 暴露 `/api/sources/audit-schedules` 和 `/api/sources/audit-jobs/tick`。
- Pending: Codex/系统级 wakeup 或常驻后台进程调用 tick；默认仍不做隐藏全盘扫描。

### M10: Obsidian MOC Writeback

- Done: `pska_obsidian_moc_propose` 从明确 source refs 生成 Obsidian MOC preview。
- Done: `pska_obsidian_moc_apply` 只允许 `obsidian_vault` root 且 permission 为
  `native_write` 或 `managed` 时写回。
- Done: apply 只创建或替换目标 note 中 `<!-- PSKA:MOC:BEGIN -->` 到
  `<!-- PSKA:MOC:END -->` 的 PSKA-managed block，保留其他用户内容。
- Done: MOC proposal 支持 `group_by="none"|"folder"|"tag"|"topic"|"project"`，
  payload 暴露 `groups`，rendered preview 会按分组输出 Markdown。
- Done: Product API 暴露 `/api/sources/obsidian/moc/proposals` 和
  `/api/sources/obsidian/moc/{proposal_id}/apply`。
- Done: source audit 对 native/managed Obsidian vault 的 unlinked notes 会给出
  `propose_obsidian_moc` next action。
- Pending: richer frontmatter fields、系统级 wakeup、EXIF/video 媒体查重。

## Non-Goals

- 不做全盘搜索守护进程。
- 不让 PSKA 持有原文副本作为 canonical source。
- 不把 Obsidian 当数据库强写。
- 不用 embedding 作为第一版检索前提。
- 不让 Hermes 直接调用文件删除、移动、Graphiti 写入或 RAGFlow 私有 API。
- 不把 every chunk、every note、every chat 都转成 memory。
- 不把泛泛的“个性化记忆摘要”当成合格 durable memory。

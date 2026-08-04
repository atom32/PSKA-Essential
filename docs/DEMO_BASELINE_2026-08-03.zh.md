# PSKA Demo Baseline 2026-08-03

本文冻结当前可演示系统的 baseline。它不是最终产品说明，也不是历史设计全集；
它只回答一个问题：今天这套以 PSKA-Essential 为胶水层、以成熟组件为能力来源的
系统，哪些能力已经可以作为 demo 使用，哪些能力明确不在当前 demo 范围内。

2026-08-04，本 demo baseline 已被
[`ALPHA_V1_BASELINE_2026-08-04.zh.md`](ALPHA_V1_BASELINE_2026-08-04.zh.md)
引用为 PSKA 组件化 Alpha v1 的封板基础。

## Baseline 结论

当前 demo 已经足够作为阶段性基线：

```text
Hermes-WebUI = 日常主入口
Eidolia = 创作画布 / 创作工作区
PSKA-Essential = 证据、scope、memory、review、审计和 provider 胶水层
RAGFlow = 文档库、解析、chunk、embedding、retrieval 后台
SQLite Memory = 当前轻量长期记忆 provider
SQLite Review = 当前轻量 review store
```

PSKA 不再做 chat，不拥有生成 LLM，也不尝试管理完整文件系统。它的价值是让
Hermes、Eidolia、RAGFlow 和 memory/review 后端通过稳定协议协作。

## 当前运行边界

| 组件 | 地址/入口 | 说明 |
| --- | --- | --- |
| Hermes WebUI | `0.0.0.0:8787` | 日常入口，可局域网访问，已有访问密码 |
| Eidolia | `127.0.0.1:8797` | 创作工作区，只给本机和 WebUI sidecar 访问 |
| PSKA Product API | `127.0.0.1:8765` | 状态、scope、retrieval probe、memory、review、jobs |
| RAGFlow API | `127.0.0.1:9380` | RAGFlow 后台 API，由 PSKA adapter 使用 |
| Hermes Agent/CLI | `~/.hermes/hermes-agent` | 推理和生成执行层 |

当前 Hermes LLM 来源是 Hermes 自身配置；最近一次本机基线为
`deepseek/deepseek-v4-flash`。PSKA 和 Eidolia 的只读证据抓取路径不直接调用 LLM。

## 当前数据集

以 PSKA Product API `/api/kb/datasets` 返回为准。当前本机 demo 数据集包括：

| 数据集 | ID | 文档/切片 | 用途 |
| --- | --- | --- | --- |
| 小米财报 | `d7a54edc8e5811f1a5cbf98514240dc5` | 2 docs / 1207 chunks | WebUI 金融分析 demo |
| 红楼梦 Hermes high readable | `ccfc1782831711f193b5db2a53339036` | 1 doc / 1 chunk | 小型连通性测试 |
| 红楼梦 Hermes UI full | `2906ace8830b11f189366f73247a116f` | 1 doc / 1695 chunks | Eidolia 文学创作证据 demo |
| 海康威视年报测试 | `ca1e8d527f4c11f189366f73247a116f` | 3 docs / 2183 chunks | 旧金融/年报 demo |

Embedding/indexing 由 RAGFlow dataset 自己配置。PSKA 只记录和传递 scope，不在
WebUI 或 Eidolia 中硬编码 embedding 服务。

## Demo Ready 流程

### 1. WebUI 金融分析

```text
用户
  -> Hermes WebUI
  -> 打开 PSKA chip，选择“小米财报”
  -> 提问
  -> Hermes 根据 turn scope 使用 PSKA/RAGFlow 证据
  -> 返回带来源的分析回答
```

已验证的问题类型：

```text
比较小米 2024 和 2025 财报中智能电动车等创新业务的收入、毛利率和亏损/利润变化，
给出 3 条金融分析要点，并列出来源。
```

期望现象：

- WebUI 显示 `PSKA scope attached to this turn.`
- PSKA audit 中出现对“小米财报”数据集的 retrieval probe / scoped retrieval。
- Hermes 返回带财报来源的回答。

### 2. Eidolia 文学创作证据抓取

```text
用户
  -> Hermes WebUI rail
  -> Eidolia
  -> 新建“检索 PSKA 证据”节点
  -> 选择红楼梦数据集
  -> 运行节点
  -> 得到 artifact/evidence 节点
```

这条路径是只读证据检索：

- 不走 Hermes。
- 不调用 LLM。
- 不写 memory。
- 不创建 review。
- 产出 evidence artifact，供后续 thought / draft 生成作为上下文。

### 3. Eidolia 创作生成

```text
Eidolia thought / pending node
  -> Hermes CLI
  -> Hermes LLM
  -> novel-local MCP / pska-essential MCP
  -> CanvasPatch
  -> Eidolia workspace
```

Eidolia 长期应只保留两类核心节点：

- `thought`：可运行的念头、推演、创作请求。
- `artifact`：文本、证据、草稿、摘录、设定等产物。

`Ask PSKA` 这类功能不应成为第三类 operator 节点；它更适合作为 artifact 的
`evidence_query` subtype 或节点动作。

### 4. Review 和 Memory 基础闭环

当前 review/memory demo 使用 SQLite：

```text
Hermes 或 API
  -> memory proposal
  -> review decision
  -> memory apply
  -> memory search
```

默认治理原则：

- 用户在对话里明确表达的低风险记忆，可以走 conversation memory auto-apply。
- 文档 digest、冲突、高风险、批处理抽取和不确定候选，进入 review。
- Review 是异常收件箱，不是日常必须清理的工作台。

## 当前不是 Demo 范围

这些点不要被误认为已经完成：

- PSKA 自己的 chat 页面。
- 在 WebUI 中重做 RAGFlow 上传/解析 UI。
- Graphiti 作为稳定主路径 memory provider。
- PSKA 直接管理完整文件系统。
- 通用文本库/BM25 文库管理。
- 完整 Office 文档资产管理。
- 把 Eidolia 复制成 WebUI 内部面板。
- 深度修改 Hermes WebUI 核心业务逻辑。

## 已知工程注意事项

- WebUI 的 PSKA chip 可能先显示 stale/loading，等待 Product API 和 dataset 状态刷新后再测试。
- 当前 WebUI chip 通过 extension/sidecar 注入 turn scope；长期目标是更结构化的 turn scope contract。
- WebUI 金融 demo 目前观测到的是 scoped retrieval/probe 审计，不应误解为每次都完整跑 PSKA agentic loop。
- PSKA MCP 当前 `tool_registry()` 暴露 51 个工具；这不是 Product API route 数量。
  Product API route 数量和 WebUI/Hermes inventory 显示口径可能不同。长期需要按
  daily/admin/dev profile 收窄。
- Hermes Agent 本地带有 MCP 修复提交；更新 upstream 前要确认该修复是否已经合入，避免 pull 后回退。
- RAGFlow 可迁移到另一台机器重新部署；PSKA 只应依赖配置化的 RAGFlow API 地址和 key。

## 不应回退的规则

1. PSKA 不做 chat，不碰最终生成 LLM。
2. WebUI 是日常入口，Eidolia 是创作工作区。
3. RAGFlow 是文档库与检索后台。
4. Memory 是增强能力，不是 evidence retrieval 的前提。
5. Review 管高风险和不确定候选，不阻塞普通问答。
6. 所有端口、地址、dataset scope、provider 都走统一配置，不能写死到业务代码。
7. PSKA 对 Hermes WebUI 的集成应尽量保持 extension/sidecar 形式，降低后续 `git pull` 成本。

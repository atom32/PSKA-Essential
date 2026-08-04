# PSKA 组件化 Alpha v1 封板说明

封板日期：2026-08-04  
版本名：`PSKA Componentized Alpha v1`  
建议 tag：`pska-alpha-v1-20260804`

本文是当前 PSKA 组件化系统的 Alpha v1 封板说明。它建立在
[`DEMO_BASELINE_2026-08-03.zh.md`](DEMO_BASELINE_2026-08-03.zh.md) 之上，
但语义不同：demo baseline 说明“现在能演示什么”，Alpha v1 说明“从今天起哪些
边界和提交被视为第一个稳定基线”。

## Alpha v1 定义

Alpha v1 不是商业 V1，也不是普通用户可无说明上手的最终产品。它的定义是：

```text
当前架构方向已经收敛；
核心组件链路已经能跑通；
主要项目 worktree 干净；
可以作为后续修 bug、做 V1.1/V2 设计和回滚的稳定锚点。
```

## 封板组件

| 组件 | 路径 | 分支 | 封板代码提交 | 角色 |
| --- | --- | --- | --- | --- |
| PSKA-Essential | `/Users/xudawei/PSKA-Essential` | `main` | `c3bb3d9a8aa10e2776d75384badb22c6f653257b` | 胶水层、Product API、MCP、memory/review 协议 |
| Eidolia / novel | `/Users/xudawei/novel` | `main` | `ae914f95a41c1d2820b19052f237fb3be90a18db` | 创作画布、Ask PSKA evidence artifact、Hermes 创作工作区 |
| Hermes-WebUI | `/Users/xudawei/hermes-webui` | `master` | `320789ae596a3963d726d90f6c7f3bc86f7f2d6d` | 日常主入口、extension 容器、Hermes 对话 UI |

说明：PSKA-Essential 的表中提交是封板前最后一个代码/文档基线提交。本封板说明
自身会产生一个 release metadata commit，`pska-alpha-v1-20260804` tag 应落在该
metadata commit 上。

说明：`hermes-webui` 当前 remote 指向上游 `nesquena/hermes-webui.git`。Alpha v1
以 commit hash 记录它的本地封板状态；不向上游仓库主动推送 PSKA tag。

## 运行时基线

2026-08-04 本机健康检查：

```text
PSKA Product API: ok
retrieval provider: ragflow
kb provider: ragflow
memory provider: sqlite
dev_fake: false
workspace_id: default
memory_namespace: workspace:default
durable_memory: manual_review
conversation_memory: auto_apply
digest_memory: manual_review
review_queue_role: exception_inbox
```

主要本机地址：

| 服务 | 地址 | 说明 |
| --- | --- | --- |
| Hermes WebUI | `0.0.0.0:8787` | 日常主入口 |
| Eidolia | `127.0.0.1:8797` | 创作工作区，由 WebUI sidecar 打开 |
| PSKA Product API | `127.0.0.1:8765` | 本机 API / sidecar / diagnostics |
| RAGFlow API | `127.0.0.1:9380` | 文档库和检索后台 |

## Alpha v1 已封能力

### 1. 系统定位

```text
Hermes-WebUI = 日常主入口
Eidolia = 创作画布 / 创作工作区
PSKA-Essential = 证据、scope、memory、review、审计和 provider 胶水层
RAGFlow = 文档库、解析、chunk、embedding、retrieval 后台
SQLite Memory = 当前轻量长期记忆 provider
SQLite Review = 当前轻量 review store
```

PSKA 不做 chat，不拥有生成 LLM，不替代 RAGFlow，不直接管理完整文件系统。

### 2. WebUI + PSKA 财报问答

WebUI 可以通过 PSKA chip 选择知识库 scope，让 Hermes 在回答时带上 PSKA/RAGFlow
证据。小米财报和海康财报数据集可作为金融分析 demo。

### 3. Eidolia + PSKA 创作证据

Eidolia 可通过 `Ask PSKA` / `Fetch PSKA Evidence` 语义创建只读证据 artifact。
这条路径：

- 走 PSKA Product API retrieval probe。
- 读 RAGFlow。
- 不走 Hermes。
- 不调用 LLM。
- 不写 memory。
- 不创建 review。

证据 artifact 可作为后续 thought / draft 的上下文。

### 4. Eidolia 创作画布交互

Alpha v1 已包含：

- thought / artifact 为核心节点语义；
- pending run target 作为待运行生成任务；
- Ask PSKA 结果节点就地更新；
- 大项目 workspace 分块传输；
- 点击节点/关系时按方向高亮邻接节点：输入/起点为黄色，输出/终点为蓝色。

### 5. Review + Memory 基础闭环

当前 memory/review 使用 SQLite。清晰的对话记忆可 auto-apply；批处理、digest、
冲突、高风险和不确定候选进入 review。Review 是异常收件箱，不是日常记忆编辑器。

## Alpha v1 不包含

- PSKA 自己的 chat。
- WebUI 内重做 RAGFlow 上传解析 UI。
- Graphiti 作为稳定主路径。
- 完整文件系统托管/分类/去重。
- 通用 BM25 文库管理。
- 完整 Office 文档管理。
- 商业化包装、销售 demo、权限体系、多租户部署。
- MCP profile 实现。

## 封板后的规则

1. Alpha v1 只修 bug，不临时加新功能。
2. 新功能进入 Alpha+1 / V1.1 / V2 backlog。
3. 不在 PSKA 里恢复 chat。
4. 不把 provider 专属能力绕过 PSKA contract 直接暴露给 Hermes。
5. 不把 WebUI core 改成强耦合 PSKA；继续优先 extension / sidecar。
6. 不把 Eidolia 的 Ask PSKA 变成生成 LLM 路径；生成走 Hermes，证据抓取保持只读。
7. RAGFlow、Eidolia、Hermes-WebUI 的地址、scope、provider 都应走配置，不写死到业务逻辑。

## 下一阶段 Backlog

优先级最高的不是继续堆功能，而是降低日常复杂度：

- MCP profile：`daily / curator / admin / dev`。
- WebUI chip 从隐藏文本注入升级为结构化 turn scope。
- 上传文档走 `curator` profile，和普通问答工具面分开。
- 做可见 audit timeline，展示 query -> scope -> retrieval -> source -> answer。
- 做 memory governance magic moment，展示 auto-apply 与 review-required 的差异。
- 整理 RAGFlow 迁移到远端机器的部署手顺。

## 复现入口

日常入口：

```text
http://127.0.0.1:8787
```

PSKA 诊断：

```text
http://127.0.0.1:8765
```

主要文档：

- [`DEMO_BASELINE_2026-08-03.zh.md`](DEMO_BASELINE_2026-08-03.zh.md)
- [`SYSTEM_INTERACTION_MODEL.zh.md`](SYSTEM_INTERACTION_MODEL.zh.md)
- [`OPERATION_MANUAL.zh.md`](OPERATION_MANUAL.zh.md)
- [`HERMES_WEBUI_INTEGRATION.md`](HERMES_WEBUI_INTEGRATION.md)
- [`REVIEW_MEMORY_PROTOCOL.md`](REVIEW_MEMORY_PROTOCOL.md)

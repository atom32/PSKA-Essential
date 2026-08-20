# Feature Evidence Matrix

| 镜头 | 用户看到什么 | 证明的组件 | 关键边界 |
| --- | --- | --- | --- |
| WebUI entry | Hermes WebUI chat 与 `pska-mini` chip | Hermes WebUI + extension loader | PSKA 没有独立产品前端 |
| Extension status | API/KB/Memory 状态、sidecar 连接 | WebUI extension sidecar + PSKA Product API | 浏览器不直连 provider |
| Scope selection | dataset/document/mode/max tokens | PSKA turn scope | scope 显式，不默默扩大 |
| Jarvis Brief | workspace/source/memory/review/next actions | `POST /api/jarvis/briefing` / `pska_jarvis_briefing` | briefing 不生成答案、不写记忆 |
| Agentic Brief | evidence/source/memory/trace/actions | `POST /api/agentic/context-brief` / `pska_agentic_context_brief` | 回答前上下文装配，不替代 Hermes |
| Source Recall | `PSKA Hermes Extension Architecture` 等本地 source search 结果 | `POST /api/sources/roots` + scan + `POST /api/sources/search` / `pska_source_search` | metadata-first，无 embedding 必需 |
| Chat Injection | Hermes chat 发送普通问题 | `knowledge-retrieval` skill + PSKA runtime scope | 不走独立 Ask 页面 |
| Memory Review | Memory / Review Queue 页面 | PSKA memory/search/review/apply routes | durable memory 需要治理 |
| Projection | Kanban `pska-review` 与 Digest Runner | Hermes Kanban/Tasks + PSKA authority | Hermes 是工作视图，PSKA 是权威源 |
| Eidolia Bridge | Eidolia rail + iframe workspace | Eidolia WebUI extension + PSKA Eidolia trace/source bridge | Eidolia 是创作区，不是 PSKA 前端 |

## Agentic 介入点

这条 demo 不是机械执行脚本。需要展示的 agentic 介入点有三类：

- **回答前上下文装配**：Agentic Brief 把 evidence、source recall、memory、trace 组合成可给 Hermes 使用的 brief。
- **对话时工具入口**：Hermes chat turn 通过 `PSKA-Mini Runtime Scope` 强制进入 `knowledge-retrieval` skill 和 PSKA MCP 工具路径。
- **日常治理入口**：review、memory apply、digest task 和 Kanban projection 都是 agent 可以接手的操作点，但 durable write 仍受 PSKA gate 约束。

## 不作为完成证据的东西

- 只录 legacy diagnostic UI。
- 只展示静态架构图。
- 只生成无浏览器操作的 slide video。
- 只跑 Product API curl，不打开 Hermes WebUI。
- 只展示 source search，不展示 chat turn scope 注入。

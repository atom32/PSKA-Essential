# PSKA 前端边界审计：Hermes WebUI Extension vs 本地诊断页

日期：2026-08-15

## 结论

PSKA v1 不应有独立用户前端。用户主入口是 Hermes WebUI；PSKA 是胶水层后端、Product API、MCP 工具、adapter boundary、review/audit/memory governance，以及 Hermes WebUI extension。

当前仓库里的 `src/pska_essential/web/*` 是本地诊断页。它可以保留用于 Product API smoke test、fake-mode 后端能力验证和开发调试，但不能作为产品演示、日常工作台或 PSKA 独立平台来推进。

之前生成的 `demo/browser/pska_webui_demo/*` 录屏素材展示的是本地诊断页，不是 Hermes WebUI 的 `pska-mini` extension。旧生成链路已经硬禁用；历史素材不能作为对用户展示的功能演示成片，也不能作为当前功能完成证据。

## 本机检查结果

`/Users/xudawei/hermes-webui` 当前没有 PSKA core panel，也没有 `/api/pska/*` 代码。PSKA 接入靠 Hermes 的通用 extension/sidecar 机制加载：

```text
~/.hermes/webui-local-extensions/pska-mini
```

仓库源代码对应：

```text
integrations/hermes-webui-extension/pska-mini/
```

extension manifest 明确是 thin Hermes-WebUI controls，sidecar origin 是：

```text
http://127.0.0.1:8765
```

也就是说，当前真实架构是：

```text
Hermes WebUI
  -> pska-mini extension
    -> /api/extensions/pska-mini/sidecar/*
      -> PSKA Product API

Hermes Agent
  -> PSKA MCP tools
    -> PSKA Core / adapters / review / audit / memory governance
```

## 现有 Extension 能力

`pska-mini` 当前提供：

- composer chip；
- PSKA enable/disable；
- dataset/document scope 选择；
- Hermes profile/project/workspace scope suggestion；
- PSKA API health、workspace status、diagnostics preview；
- RAGFlow retrieval probe；
- `knowledge-retrieval` skill 加载；
- next chat start 的 `PSKA-Mini Runtime Scope` 注入；
- PSKA Memory 小页面；
- review queue 查看、accept、reject、apply-memory；
- review 到 Hermes Kanban `pska-review` 的只读/幂等投影；
- Hermes Tasks 里的 `PSKA Digest Runner` 入口。

它刻意不提供：

- PSKA chat；
- Eidolia 页面；
- 独立 Ask panel；
- upload UI；
- RAGFlow/Graphiti 浏览器直连。

这个方向是对的：extension 是 Hermes 里的薄控制面，不是替代 Hermes 的产品壳。

## 重复与越界

`src/pska_essential/web/*` 诊断页已经实现了完整侧栏和多页面工作台：

- Home / Jarvis briefing；
- KB 创建、上传、解析、readiness；
- Ask；
- Sources 注册、扫描、审计、搜索、去重、tag/comment/MOC；
- Memory cards、health、briefing、timeline、why-used；
- Review queue、revision、batch decision、apply-memory；
- Activity audit；
- Settings、diagnostics、probe、eval。

这些能力本身属于 PSKA Product API/MCP/Core，是有价值的；但作为浏览器产品界面时，它和 Hermes WebUI 的职责重复：

| 功能 | 诊断页现状 | Hermes/extension 正确归属 |
| --- | --- | --- |
| Chat / Ask | 诊断页有独立 Ask 页面 | 日常问答走 Hermes chat + PSKA MCP/turn scope；面板 Ask 只能是辅助，不应成为主路径 |
| KB ingest | 诊断页有上传/解析 UI | 用户路径应在 Hermes WebUI panel/proxy 或 Hermes agent tool；PSKA 只管 Product API/MCP |
| Memory 管理 | 诊断页有完整 memory cards 和 review queue | 日常记忆编辑走 Hermes 对话中的 remember/correct/forget；异常进 PSKA review |
| Review | 诊断页可决策和 apply | Hermes WebUI 中投影/处理，仍调用 PSKA Product API |
| Sources | 诊断页有 source root/search/dedup/tag/comment | Agentic 文件治理应由 Hermes agent 调 PSKA tools；需要 UI 时做 Hermes panel |
| Trace/Audit | 诊断页有 Activity | Hermes tool cards + PSKA trace/audit drawer/panel |

## 修正原则

1. `src/pska_essential/web/*` 改名义：legacy local diagnostic UI。
2. 不再把诊断页录屏称为 PSKA WebUI 产品演示。
3. 新用户演示必须录制 Hermes WebUI：PSKA chip、scope、chat、MCP/tool cards、sidecar、review/task 投影。
4. 新的用户可见前端能力优先落在 `integrations/hermes-webui-extension/pska-mini/*` 或 Hermes WebUI proxy/panel，不继续扩张诊断页。
5. 诊断页可以继续覆盖后端能力，作为本机检查、fake-mode 演练和开发调试入口。

## 下一条演示线

正确的功能演示视频应按这个路径录制：

1. 打开 Hermes WebUI `http://127.0.0.1:8787`。
2. 展示 Settings -> Extensions 中 `pska-mini` 已加载，sidecar health 指向 PSKA Product API。
3. 在 composer chip 选择 PSKA scope。
4. 在 chip 内触发 Jarvis Brief、Agentic Brief、Source Recall，展示回答前由 PSKA 组装来源、记忆、trace 和下一步动作。
5. 发起 Hermes chat turn，确认 turn context 注入而不是独立 Ask 页面。
6. 展示 Hermes 使用 PSKA MCP tools 或 `knowledge-retrieval` skill。
7. 展示回答中的来源、工具调用、scope、memory attribution。
8. 打开 PSKA Memory/Review projection，处理一个 review 或展示 apply-memory gate。
9. 展示 Kanban `pska-review` 和 `PSKA Digest Runner` 任务投影。
10. 展示 Eidolia 入口只作为 Hermes WebUI 内嵌创作工作区，PSKA 通过 Eidolia trace/source bridge 读取创作上下文。

本地诊断页录屏不再作为演示交付物；只能在明确标注为 legacy diagnostic smoke path 的内部排查中参考，不能放进主视频冒充真实产品入口。

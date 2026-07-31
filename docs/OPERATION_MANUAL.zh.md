# PSKA-Essential 操作手册

本文面向今天的可运行系统：Hermes WebUI 日常入口、真实 RAGFlow
知识库与检索、PSKA Product API/MCP、显式 memory substrate，以及作为异常收件箱的 Review。

## 1. 启动前确认

确认当前主路径组件在线：

```bash
curl http://127.0.0.1:9380/api/v1/system/ping
curl http://127.0.0.1:8765/api/health
```

预期：

- RAGFlow 返回 `pong`
- PSKA Product API 返回 `ok: true`

Graphiti 只有在 `PSKA_MEMORY_PROVIDER=graphiti` 时才是必需组件。当前轻量路径
使用 `PSKA_MEMORY_PROVIDER=sqlite`，因此 evidence retrieval、review 和基础
memory 闭环不依赖 Graphiti。

推荐直接使用统一启动脚本：

```bash
make start-workspace
```

它会检查 RAGFlow、当前 memory provider、PSKA Product API 与 Hermes WebUI。PSKA
检查不只看 `/api/health`，还会验证 `/api/capabilities` 中的 Product API
contract，避免旧进程还活着但缺少 `/api/memory/search` 等新接口。

如果只想手动启动 PSKA Product API，可使用：

```bash
PYTHONPATH=src python3 -m pska_essential.product_api --env-file .env.pska.demo
```

日常入口是 Hermes WebUI：

```text
http://127.0.0.1:8787
```

PSKA 自带的 `http://127.0.0.1:8765` 只是诊断和调试 surface，不是日常对话前端。

说明：

- `.env.pska` 使用真实 RAGFlow KB/retrieval。
- 当前开发手顺使用 SQLite memory；它是轻量本地 memory provider，不需要 Graphiti。
- Graphiti 可以作为未来图记忆 provider 接回，但它需要自己的 LLM/embedding provider
  配置完整，不能阻塞 RAGFlow evidence retrieval。

## 2. 看系统状态

在 Hermes WebUI 中打开 PSKA 面板，或在 PSKA 诊断页面进入 `首页`：

- `知识库` 应显示已连接的 RAGFlow 数据集。
- `下一步操作` 会提示可以提问、等待 ingestion，或处理异常 Review。
- 当前可用数据集以 PSKA Product API 返回为准；本机样例包含
  `海康威视年报测试-local-embedding` 和红楼梦测试数据集。

也可用命令确认：

```bash
make workspace-status ENV_FILE=.env.pska.demo
```

## 3. 基础闭环：问答到工作产物

进入 `提问`：

1. 在知识库选择器中选择 `海康威视年报测试-local-embedding`。
2. 点击 `加入知识库`。
3. 输入问题，例如：

   ```text
   请用要点总结海康威视2025年报中的核心经营变化、主要风险和管理层重点。
   ```

4. 点击 `运行提问`。

预期结果：

- 状态为 `ready`。
- 返回多个 context packets。
- 显示 source manifest。
- 可以打开来源阅读器。
- `写作` 页面出现 sourced brief。

## 4. 导出

进入 `写作`：

- 点击 `Markdown` 或 `JSON`。
- 导出会写入 `workflow.export` audit record。
- JSON 导出包含 run、proposal、source manifest、context packets、source inspections、traceability。

## 5. 长期记忆治理

日常记忆变更不应该靠用户打开 Review。

正常路径是在 Hermes 对话中直接说：

```text
记住：我更喜欢 AMD CPU。
不对，我的主力机不是 ThinkPad，是 Framework。
忘掉刚才那条关于项目偏好的记忆。
```

Hermes 应该判断这是 remember、correct、update 还是 forget，然后调用
`pska_memory_change_from_conversation` 或
`POST /api/memory/conversation-change`。默认策略是：

```text
PSKA_GOVERNANCE_CONVERSATION_MEMORY=auto_apply
```

所以清晰、低风险、用户主动表达的记忆增删改会自动接受并写入 memory
backend，同时仍然留下 proposal、accepted review decision、memory apply 和 audit
记录。用户不用清一个日常 Review 队列。

Review 只作为异常收件箱：

- 文档 digest 或批处理抽取出的重要但不确定知识；
- 与已有记忆冲突的新证据；
- 目标不清楚、范围很大或高风险的破坏性删除/修改；
- 隐私、安全、法律、企业治理等高风险记忆；
- Agent 或用户显式设置 `force_review=true` 的变更。

如果确实需要从当前 sourced workflow 生成待确认的长期知识，可以在 `写作`
中点击 `创建异常审核`：

- PSKA 会从当前 transient workflow 创建 `memory_patch` review。
- 该 review 初始状态为 `pending`。
- 不会自动写入长期记忆，除非 workspace policy 明确配置为 auto apply。

进入 `审核` 后：

1. 打开 pending review。
2. 检查来源数量和候选内容。
3. 选择 `接受`、`需修改` 或 `拒绝`。
4. 只有接受后的 review 才能进入 apply。

这就是 PSKA 的 durable knowledge governance：普通对话修正是主路径，Review
只处理不确定、重要、冲突或高风险的 durable knowledge 变更。

## 6. 上传新文档

进入 `知识库`：

1. 选择已有知识库，或填写新知识库名称。
2. 选择文件。
3. PDF/年报类文件建议使用 RAGFlow-backed KB。
4. 点击 `上传` 只做 KB ingest。
5. 点击 `运行闭环` 会执行 upload -> readiness -> Ask -> export。

长文档 ingestion 可能很慢：

- parsing
- OCR
- chunking
- embedding
- indexing

如果未完成，PSKA 会返回 not-ready/resume contract，而不是编造答案。

## 7. 什么时候进入 memory provider

上传文件只进入 RAGFlow。

```text
Hermes WebUI / PSKA API
  -> PSKA KB adapter
  -> RAGFlow ingest
  -> RAGFlow parse/chunk/embed/index
```

Memory provider 不会因为上传或切片自动写入。它只接收紧凑、可治理的长期记忆：

- 用户在 Hermes 对话中明确说 `记住 / 不对 / 忘掉`，Hermes 调
  `pska_memory_change_from_conversation`，清晰低风险的变更可自动 apply；
- PSKA 对 ready 的 RAGFlow scope 跑 `pska_digest_scope` 或 digest job，生成
  compact digest，必要时进入异常 Review，接受并 apply 后才写 memory provider。

用下面的接口看后台队列：

```bash
curl http://127.0.0.1:8765/api/provider/jobs
```

在 Hermes WebUI 里，也可以在 PSKA Knowledge 面板的 `Digest` 卡片显式排队，
然后在 `Jobs` 卡片里查看和运行这个 digest job。

其中 `pska_digest_job` 会显示 `dataset_ids`、`document_ids`、`priority`、
`attempt_count`、readiness 和 `data_flow.writes_memory_directly=false`。
这表示 digest job 是“候选知识消化任务”，不是 memory provider 直接写入任务。

## 8. 诊断

进入 `设置`：

- `运行时`：查看当前 provider。
- `诊断`：查看 Product API、KB、retrieval、memory 状态。
- `检索探针`：验证选中知识库是否能返回 context。
- `实时闭环`：验证 readiness -> retrieval -> Ask -> source inspection -> export。
- `组件检查`：验证 runtime diagnostics、memory probe、retrieval probe、closed-loop probe。

## 9. 当前已知限制

- Graphiti 只有在选为 memory provider 时才需要健康；容器健康也不等于 Graphiti search 可用，它还需要自己的 LLM/embedding provider。
- 演示模式使用 `company_graphrag_stub` 时，它是显式 memory substrate，不是 silent fallback。
- 前端已经切到中文主界面；动态后端状态码、audit action、provider 名称仍保留英文/contract 语言。

## 10. 前端语言与 i18n

当前前端默认语言是中文。

实现方式是轻量 i18n：

- `index.html` 承载静态中文结构。
- `app.js` 顶部定义 `LOCALE = "zh-CN"` 和 `messages` 字典。
- 动态按钮、toast、空状态、诊断标签通过 `t("key")` 读取文案。
- 后端返回的 provider 名称、状态码、audit action、proposal kind 保留 contract 原文，便于定位组件问题。

以后要加英文包时，应把 `messages` 拆成 locale dictionary，而不是在业务逻辑里写 `if language == ...`。

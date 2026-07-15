# PSKA-Essential 操作手册

本文面向今天的可运行系统：真实 RAGFlow 知识库与检索、PSKA 前端/API、显式 memory substrate、人工 review gate。

## 1. 启动前确认

确认外部组件在线：

```bash
curl http://127.0.0.1:9380/api/v1/system/ping
curl http://127.0.0.1:8000/healthcheck
```

预期：

- RAGFlow 返回 `pong`
- Graphiti 返回 `{"status":"healthy"}`

当前演示建议使用：

```bash
PYTHONPATH=src python3 -m pska_essential.product_api --env-file .env.pska.demo
```

然后打开：

```text
http://127.0.0.1:8765
```

说明：

- `.env.pska.demo` 使用真实 RAGFlow KB/retrieval。
- memory provider 显式设置为 `company_graphrag_stub`，用于今天演示完整 review/apply 生命周期。
- `.env.pska` 可切回 Graphiti，但 Graphiti search 需要先补齐自己的 LLM/embedding provider 配置。

## 2. 看系统状态

进入 `首页`：

- `知识库` 应显示已连接的 RAGFlow 数据集。
- `下一步操作` 会提示可以提问、审核或等待 ingestion。
- 当前可用数据集为 `海康威视年报测试-local-embedding`，应有 615 个 chunks。

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

## 5. 长期知识治理

在 `写作` 中点击 `记忆审核`：

- PSKA 会从当前 transient workflow 创建 `memory_patch` review。
- 该 review 初始状态为 `pending`。
- 不会自动写入长期记忆。

进入 `审核`：

1. 打开 pending review。
2. 检查来源数量和候选内容。
3. 选择 `接受`、`需修改` 或 `拒绝`。
4. 只有接受后的 review 才能进入 apply。

这就是 PSKA 的 durable knowledge governance：普通工作产物可以自由生成，长期知识必须通过治理。

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

## 7. 诊断

进入 `设置`：

- `运行时`：查看当前 provider。
- `诊断`：查看 Product API、KB、retrieval、memory 状态。
- `检索探针`：验证选中知识库是否能返回 context。
- `实时闭环`：验证 readiness -> retrieval -> Ask -> source inspection -> export。
- `组件检查`：验证 runtime diagnostics、memory probe、retrieval probe、closed-loop probe。

## 8. 当前已知限制

- Graphiti 容器健康不等于 Graphiti search 可用。当前 Graphiti search 报 500，需要配置它自己的 LLM/embedding provider。
- 演示模式使用 `company_graphrag_stub` 作为显式 memory substrate，不是 silent fallback。
- 前端已经切到中文主界面；动态后端状态码、audit action、provider 名称仍保留英文/contract 语言。

## 9. 前端语言与 i18n

当前前端默认语言是中文。

实现方式是轻量 i18n：

- `index.html` 承载静态中文结构。
- `app.js` 顶部定义 `LOCALE = "zh-CN"` 和 `messages` 字典。
- 动态按钮、toast、空状态、诊断标签通过 `t("key")` 读取文案。
- 后端返回的 provider 名称、状态码、audit action、proposal kind 保留 contract 原文，便于定位组件问题。

以后要加英文包时，应把 `messages` 拆成 locale dictionary，而不是在业务逻辑里写 `if language == ...`。

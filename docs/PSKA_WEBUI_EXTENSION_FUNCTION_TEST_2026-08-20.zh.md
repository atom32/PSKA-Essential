# PSKA Hermes WebUI Extension 功能点测试报告

日期：2026-08-20

## 测试对象

测试对象是 Hermes WebUI 内的 `pska-mini` extension，不是 PSKA 本地诊断页。

入口：

```text
Hermes WebUI: http://127.0.0.1:8787
Extension: pska-mini
Sidecar target: http://127.0.0.1:8765
```

测试使用 WebUI 登录 session、WebUI sidecar 代理、WebUI CSRF token 和真实本机服务。测试脚本：

```text
/Users/xudawei/PSKA-Essential/scripts/test_pska_webui_extension.mjs
```

运行方式：

```bash
cd /Users/xudawei/PSKA-Essential
HERMES_WEBUI_PASSWORD=****** node scripts/test_pska_webui_extension.mjs
```

## 第一轮问题

第一轮测试结果：

```text
total=28
passed=22
failed=6
```

失败项：

```text
Hermes context: active profile
Button: Jarvis Brief
Button: Agentic Brief
Memory Page: create review candidate
Memory Page: review detail
Memory Page: reject temporary candidate
```

其中 active profile 和 Memory Create 有一部分是测试脚本 payload 与当前页面实现不一致；真正的页面级问题是：

```text
Button: Jarvis Brief -> 502 Extension sidecar response too large
Button: Agentic Brief -> 502 Extension sidecar response too large
```

直接调用 PSKA Product API 复核：

```text
Jarvis Brief full response: 552077 bytes
Agentic Brief full response: 674966 bytes
Hermes WebUI sidecar response limit: 512 * 1024 bytes
```

结论：后端能生成 brief，但 WebUI extension 通过 sidecar 拿不到完整响应，所以页面按钮会失败。

## 修复

本轮修复了：

1. `POST /api/jarvis/briefing` 支持 `compact=true` 或 `view=webui`。
2. `POST /api/agentic/context-brief` 支持 `compact=true` 或 `view=webui`。
3. `pska-mini` extension 的 Jarvis Brief 和 Agentic Brief 请求改为 compact 模式。
4. 新增 WebUI extension 合同测试脚本。
5. 新增 unittest，防止 WebUI brief 再返回超大内部层。

compact 复核：

```text
Jarvis Brief compact response: 7891 bytes
Agentic Brief compact response: 41950 bytes
```

## 最终测试结果

修复后重新运行：

```text
total=29
passed=29
failed=0
```

通过的功能点：

```text
WebUI login
WebUI root page loads
Extension manifest loads
Extension JS loads and contains handlers
Extension CSS loads
Sidecar health through WebUI
Dashboard: workspace status
Dashboard: KB datasets
Dashboard: runtime diagnostics
Hermes context: active profile
Hermes context: projects
Hermes context: workspaces
Button: RAGFlow Probe
Button: Preview memory-only
Button: Preview dataset scoped
Button: Jarvis Brief
Button: Agentic Brief
Button: Source Recall
Memory Page: search
Memory Page: review list pending
Memory Page: create review candidate
Memory Page: review detail
Memory Page: reject temporary candidate
Kanban: list/create PSKA board
Kanban: create one projected task
Kanban: archive temporary projected task
Digest Task: list Hermes tasks
Digest Task: create or find
Chat bridge dependency: skill content
```

## 污染检查

测试中创建了临时候选 review，并立即拒绝。

复核结果：

```text
Memory health: card_count=10, issue_count=0
Active memory ids: 2-11
临时候选 pending: 0
临时候选 rejected: rev_prop_4ab693cef2774633b9adc5edee9d2bc8 等测试候选
```

测试没有写入长期记忆。

Kanban 测试中创建的 `PSKA test projection ...` 临时任务现在由测试脚本自动通过
WebUI `/api/kanban/tasks/<id>/patch` 归档。复核 `pska-review` 看板默认视图后，可见任务中已无测试投影卡片。

## 仍需注意

这次测试是 WebUI sidecar/API 合同测试，不是完整视觉点击测试。它验证了页面按钮实际会调用的路径、认证、CSRF、sidecar、后端响应和写入保护，但没有做像素级截图和鼠标点击回放。

如要继续做视觉层测试，需要补 Playwright 或浏览器控制工具，检查：

- chip 是否出现在正确位置；
- 菜单打开/关闭是否正常；
- preview 文本是否在页面上正确显示；
- 移动端按钮是否可见；
- Memory Page 布局是否没有遮挡；
- Kanban/Tasks 投影在 Hermes UI 里是否好看、可理解。

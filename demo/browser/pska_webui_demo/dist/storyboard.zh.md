# PSKA Product API 诊断页浏览器操作素材 Storyboard

Version: M32-browser-demo

## 01. 打开 PSKA 诊断页

Time: `00:00:00.000` - `00:00:20.019`
Screenshot: `capture/00_home.png`
Cursor: `[1168, 278]`

Home 页面显示 API 已连接、1 个知识库，以及 Jarvis briefing 的资料源和记忆信号。

Narration: 先打开 PSKA 本地诊断页。这里不是 Hermes WebUI extension，而是连接本地 Product API 的 smoke path，用来检查知识库数量、Jarvis briefing、资料源状态和最近记忆提示。

## 02. 生成 Agentic Context Brief

Time: `00:00:20.019` - `00:00:34.863`
Screenshot: `capture/01_context_brief.png`
Cursor: `[1038, 395]`

点击生成 Brief 后，系统把 evidence、source recall、memory、trace 和 next actions 放到同一张工作上下文里。

Narration: 点击生成 Brief 后，PSKA 先组织回答前上下文。它同时拉取知识库 evidence、本地 source recall、可治理记忆、trace 信号和下一步动作。

## 03. 从 Brief 进入 Ask

Time: `00:00:34.863` - `00:00:48.420`
Screenshot: `capture/02_ask_prefill.png`
Cursor: `[710, 335]`

Brief 的 next action 进入提问页，知识库 scope 已自动带入，不需要重新手填。

Narration: 从 Brief 的 next action 进入 Ask 页面，知识库 ID 已经自动带入。也就是说，Hermes 不是凭感觉回答，而是先接上当前可用的上下文范围。

## 04. 填写问题并运行

Time: `00:00:48.420` - `00:01:01.132`
Screenshot: `capture/03_ask_result.png`
Cursor: `[343, 631]`

问题要求系统证明这是浏览器演示，并同时展示 source recall、memory、trace 和 next actions。

Narration: 这里填入一个验证型问题：要求系统证明这是一次真实浏览器演示，并在回答里展示 source recall、memory、trace 和 next actions。

## 05. 得到带来源 Brief

Time: `00:01:01.132` - `00:01:15.021`
Screenshot: `capture/04_ask_result_brief.png`
Cursor: `[580, 698]`

结果里有 run id、source count、inspected source count、used memory count、Source Manifest 和 Memory Attribution。

Narration: 运行后得到带来源 Brief。画面里可以看到 run id、source 数量、已检查 source 数量、使用记忆数量，以及 Source Manifest 和 Memory Attribution。

## 06. 查看 Agentic Loop Trace

Time: `00:01:15.021` - `00:01:29.308`
Screenshot: `capture/05_loop_trace.png`
Cursor: `[1177, 648]`

Loop 明确列出 scope、governance、readiness、retrieval、memory.search、source.inspect 等步骤。

Narration: 继续下滚可以看到 Agentic Loop。它把 scope check、governance policy、knowledge readiness、retrieval plan、memory search 和 source inspection 都记录成可检查步骤。

## 07. 记忆不是空泛摘要

Time: `00:01:29.308` - `00:01:42.212`
Screenshot: `capture/06_memory_cards.png`
Cursor: `[1168, 346]`

Memory 页展示最近使用的 Memory Card，并能追问为什么用到、查看时间线和来源。

Narration: 记忆页面展示最近被使用的 Memory Card。它不是一句空泛画像，而是能查看为什么用到、时间线、来源和 review 状态的治理对象。

## 08. 审计记录支撑可追溯

Time: `00:01:42.212` - `00:01:53.259`
Screenshot: `capture/07_activity_trace.png`
Cursor: `[985, 153]`

Activity 页记录 agentic_loop.complete，并保留 run、ready、context 等审计标签。

Narration: Activity 页面保存审计记录。这里能看到 agentic loop complete，对应刚才那次提问的 run、ready 状态和 context 数量。

## 09. 接入本地资料源

Time: `00:01:53.259` - `00:02:06.627`
Screenshot: `capture/08_sources.png`
Cursor: `[1084, 423]`

Sources 页展示本地文件夹资料源：read only、scanned、objects 1，并提供扫描、抽取、审计入口。

Narration: 资料源页面展示已经注册的本地文件夹。当前权限是 read only，状态已扫描，有一个对象，并提供扫描、队列抽取和审计入口。

## 10. 无 embedding 搜索命中文件

Time: `00:02:06.627` - `00:02:21.215`
Screenshot: `capture/09_sources_search.png`
Cursor: `[329, 305]`

no-embedding search 查询 browser demo，命中本地 Markdown 文件 pska-demo-note.md，并显示来源行号和匹配摘要。

Narration: 最后演示无 embedding 搜索。输入 browser demo 后，系统命中本地 Markdown 文件 pska-demo-note.md，并显示来源、行号、索引状态和匹配摘要。

# PSKA Diagnostic Page Playwright Recording Storyboard

## 01. 打开 PSKA 诊断页

Time: `00:00:01.594` - `00:00:04.413`

真实浏览器连接本地 Product API，Home 显示知识库、Jarvis briefing、资料源和记忆信号。

## 02. 点击生成 Agentic Context Brief

Time: `00:00:04.413` - `00:00:08.241`

PSKA 在回答前组合 KB evidence、本地 source recall、Memory Card、trace 信号和 next actions。

## 03. 从 Brief 的 next action 进入 Ask

Time: `00:00:08.241` - `00:00:10.184`

点击 Brief 中的提问动作，Ask 页面自动带入 ready knowledge scope。

## 04. 填写问题并运行 Ask

Time: `00:00:10.184` - `00:00:13.995`

问题要求系统在浏览器中证明 source recall、memory、trace 和 next actions 都真的被用上。

## 05. 查看带来源 Brief

Time: `00:00:13.995` - `00:00:17.943`

结果包含 run id、source count、inspected source count、used memory count、Source Manifest 和 Memory Attribution。

## 06. 查看 Agentic Loop Trace

Time: `00:00:17.943` - `00:00:21.591`

Loop 展示 scope.check、governance.policy、kb.readiness、retrieval.plan、memory.search 和 source.inspect。

## 07. 打开 Memory Card 页面

Time: `00:00:21.591` - `00:00:26.242`

Memory 页面展示最近使用的记忆卡片，并提供为什么用到、时间线、查看等治理入口。

## 08. 打开 Activity 审计记录

Time: `00:00:26.242` - `00:00:30.191`

Activity 页面展示刚才 Ask 产生的 agentic_loop.complete，以及 run、ready、context 等审计标签。

## 09. 打开 Sources 本地资料源

Time: `00:00:30.191` - `00:00:33.824`

Sources 页面展示 read only、scanned、objects 1 的本地文件夹，并保留扫描、抽取和审计入口。

## 10. 运行无 embedding 搜索

Time: `00:00:33.824` - `00:00:38.275`

在 Sources 中搜索 browser demo，命中本地 Markdown 文件 pska-demo-note.md，并显示行号和摘要。

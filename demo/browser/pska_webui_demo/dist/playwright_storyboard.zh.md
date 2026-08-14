# PSKA WebUI Playwright Recording Storyboard

## 01. 打开 PSKA WebUI

Time: `00:00:01.636` - `00:00:04.450`

真实浏览器连接本地 Product API，Home 显示知识库、Jarvis briefing、资料源和记忆信号。

## 02. 点击生成 Agentic Context Brief

Time: `00:00:04.450` - `00:00:08.260`

PSKA 在回答前组合 KB evidence、本地 source recall、Memory Card、trace 信号和 next actions。

## 03. 从 Brief 的 next action 进入 Ask

Time: `00:00:08.260` - `00:00:10.205`

点击 Brief 中的提问动作，Ask 页面自动带入 ready knowledge scope。

## 04. 填写问题并运行 Ask

Time: `00:00:10.205` - `00:00:14.013`

问题要求系统在浏览器中证明 source recall、memory、trace 和 next actions 都真的被用上。

## 05. 查看带来源 Brief

Time: `00:00:14.013` - `00:00:17.960`

结果包含 run id、source count、inspected source count、used memory count、Source Manifest 和 Memory Attribution。

## 06. 查看 Agentic Loop Trace

Time: `00:00:17.960` - `00:00:21.594`

Loop 展示 scope.check、governance.policy、kb.readiness、retrieval.plan、memory.search 和 source.inspect。

## 07. 打开 Memory Card 页面

Time: `00:00:21.594` - `00:00:26.248`

Memory 页面展示最近使用的记忆卡片，并提供为什么用到、时间线、查看等治理入口。

## 08. 打开 Activity 审计记录

Time: `00:00:26.248` - `00:00:30.193`

Activity 页面展示刚才 Ask 产生的 agentic_loop.complete，以及 run、ready、context 等审计标签。

## 09. 打开 Sources 本地资料源

Time: `00:00:30.193` - `00:00:33.826`

Sources 页面展示 read only、scanned、objects 1 的本地文件夹，并保留扫描、抽取和审计入口。

## 10. 运行无 embedding 搜索

Time: `00:00:33.826` - `00:00:38.308`

在 Sources 中搜索 browser demo，命中本地 Markdown 文件 pska-demo-note.md，并显示行号和摘要。

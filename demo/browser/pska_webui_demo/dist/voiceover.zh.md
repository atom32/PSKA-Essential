# PSKA WebUI 浏览器操作演示 Voiceover

旁白稿可直接用于重新录音或导入剪映。

## 01. 打开 PSKA WebUI

先打开真实的 PSKA WebUI。这里不是静态幻灯片：页面已经连接本地 Product API，首页能看到知识库数量、Jarvis briefing、资料源状态和最近记忆提示。

## 02. 生成 Agentic Context Brief

点击生成 Brief 后，PSKA 先组织回答前上下文。它同时拉取知识库 evidence、本地 source recall、可治理记忆、trace 信号和下一步动作。

## 03. 从 Brief 进入 Ask

从 Brief 的 next action 进入 Ask 页面，知识库 ID 已经自动带入。也就是说，Hermes 不是凭感觉回答，而是先接上当前可用的上下文范围。

## 04. 填写问题并运行

这里填入一个验证型问题：要求系统证明这是一次真实浏览器演示，并在回答里展示 source recall、memory、trace 和 next actions。

## 05. 得到带来源 Brief

运行后得到带来源 Brief。画面里可以看到 run id、source 数量、已检查 source 数量、使用记忆数量，以及 Source Manifest 和 Memory Attribution。

## 06. 查看 Agentic Loop Trace

继续下滚可以看到 Agentic Loop。它把 scope check、governance policy、knowledge readiness、retrieval plan、memory search 和 source inspection 都记录成可检查步骤。

## 07. 记忆不是空泛摘要

记忆页面展示最近被使用的 Memory Card。它不是一句空泛画像，而是能查看为什么用到、时间线、来源和 review 状态的治理对象。

## 08. 审计记录支撑可追溯

Activity 页面保存审计记录。这里能看到 agentic loop complete，对应刚才那次提问的 run、ready 状态和 context 数量。

## 09. 接入本地资料源

资料源页面展示已经注册的本地文件夹。当前权限是 read only，状态已扫描，有一个对象，并提供扫描、队列抽取和审计入口。

## 10. 无 embedding 搜索命中文件

最后演示无 embedding 搜索。输入 browser demo 后，系统命中本地 Markdown 文件 pska-demo-note.md，并显示来源、行号、索引状态和匹配摘要。

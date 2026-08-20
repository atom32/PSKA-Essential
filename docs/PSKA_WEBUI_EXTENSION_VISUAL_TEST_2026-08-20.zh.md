# PSKA Hermes WebUI Extension 浏览器级视觉测试报告

日期：2026-08-20

## 测试对象

测试对象是 Hermes WebUI 内的 `pska-mini` extension。

入口：

```text
Hermes WebUI: http://127.0.0.1:8787
Extension: pska-mini
```

本轮使用 Codex 内置浏览器的 Playwright 风格 API 操作真实页面，覆盖桌面视口 `1280x720` 和手机视口 `390x844`。这不是单纯 API 合同测试。

截图和结构化结果：

```text
/Users/xudawei/PSKA-Essential/docs/visual-tests/2026-08-20-pska-webui/
```

## 发现的问题

第一，PSKA 浮层首次打开时会短暂显示：

```text
API missing / KB not ready / Memory down / GBrain not visible
```

但实际服务正常。点 `Refresh` 后会变成：

```text
API ready / KB 10/10 / Memory gbrain / GBrain active
```

原因是 `refreshDashboard()` 刚开始 loading 时，`renderStatus()` 用空 dashboard 渲染成错误态。

第二，手机视口下底部 PSKA chip 被 composer 工具栏挤压，最初只能露出 `PS...`，第一次修复后又被压成只剩一个状态点，不够可识别。

## 已修复

本轮修复：

1. 首次 loading 时显示 `checking`，不再误报 `API missing`。
2. 手机端 composer 中 PSKA chip 改为紧凑标签 `PSKA`。
3. 手机端 PSKA chip 排序提前，固定 `72px`，避免被发送按钮挤压。
4. 同步到 Hermes WebUI 实际 extension 目录。

修复后复测：

```text
首次打开: API checking / KB checking / Memory checking / GBrain checking
加载完成: API ready / KB 10/10 / Memory gbrain / GBrain active
手机 chip: label=PSKA, withinViewport=true, overlapsSend=false
手机菜单: visible=true, no viewport overflow
console warnings/errors: []
```

## 覆盖结果

已截图确认：

```text
desktop-menu.png
desktop-source-recall.png
desktop-memory-page.png
mobile-chip.png
mobile-menu.png
visual-results.json
```

功能点覆盖：

```text
桌面 PSKA chip 可见
桌面菜单可打开
桌面菜单不越界
首次 loading 状态不误报错误
服务状态加载后显示 ready
Source Recall 按钮可返回可见结果
Memory Page 可从 PSKA 菜单进入
Memory Page 状态、搜索结果、审核队列可见
Memory Page 搜索、View、创建临时候选、拒绝临时候选路径已手动验证
手机 PSKA chip 可见
手机 PSKA chip 不与发送按钮重叠
手机 PSKA 菜单可打开
手机 PSKA 菜单不越界
```

## 命令行回归脚本

已新增可重复运行的视觉 smoke：

```text
/Users/xudawei/PSKA-Essential/scripts/test_pska_webui_visual.cjs
```

它覆盖：

```text
登录/会话复用
桌面菜单首次打开
桌面按钮结果
Memory Page
手机 chip
手机菜单
关键 bounding box 断言
控制台 warning/error 检查
截图和 visual-results.json 输出
```

运行方式：

```bash
cd /Users/xudawei/PSKA-Essential
HERMES_WEBUI_PASSWORD=****** \
NODE_PATH=/tmp/pska-playwright/node_modules \
PSKA_PLAYWRIGHT_MODULE=playwright-core \
PSKA_PLAYWRIGHT_CHANNEL=chrome \
make webui-extension-visual
```

脚本默认把截图写到 `/tmp/pska-webui-visual-*`，不会自动污染仓库。如需归档，可显式设置
`PSKA_VISUAL_OUT`。

本轮已在 promoted `8787` 主线端口运行通过：

```text
output_dir=/tmp/pska-webui-visual-promoted-8787-20260820-212115
ok=true
checks=7/7
console warnings/errors=0
```

覆盖结果包括：

```text
Desktop menu visible and in viewport
Desktop Source Recall returns visible results
Memory page visible with memory and review data
Mobile PSKA chip visible and not overlapping send
Mobile menu visible and in viewport
```

PSKA 仓库仍不直接引入 `playwright` 或 `@playwright/test` 依赖。需要本地视觉回归时，在仓库外准备
Playwright：

```bash
mkdir -p /tmp/pska-playwright
cd /tmp/pska-playwright
npm init -y >/dev/null
npm install playwright-core
```

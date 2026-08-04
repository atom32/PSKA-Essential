# PSKA Full Compose 部署复盘 2026-08-05

这次在远端演示笔记本上的 full compose 部署可以判定为成功。

成功标准不是“容器启动”，而是下面几条都已验证：

- Hermes-WebUI 可从局域网登录访问。
- WebUI extension manifest 正常加载 `pska-mini` 和 `eidolia`。
- WebUI sidecar proxy 可以访问 PSKA Product API 和 Eidolia。
- Eidolia 的 Agent backend 是 `hermes_gateway`，不是 `hermes_cli`。
- Hermes Agent 的 PSKA MCP 配置是内部 HTTP：`http://pska-mcp:8766/mcp`。
- PSKA Product API 使用 `ragflow` retrieval/KB provider 和 `sqlite` memory provider。
- RAGFlow 数据集 readiness 可以通过 PSKA 查询。
- Eidolia 可以创建项目、保存 canvas，并通过 Hermes Gateway 异步生成 thought 节点。
- Review + Memory 可以完成候选创建、accept、apply、search 闭环。

## 本次实际通过的链路

```text
WebUI -> extension sidecar proxy HTTP -> PSKA Product API -> RAGFlow
WebUI -> extension sidecar proxy HTTP -> Eidolia
Eidolia -> Hermes Gateway HTTP -> Hermes Agent
Hermes Agent -> PSKA MCP streamable HTTP -> PSKA-Essential
PSKA-Essential -> RAGFlow / SQLite Review / SQLite Memory
```

验证项目：

- HTML 图表生成项目：`pska-demo-html-eidolia-async-20260805001843`
- 小米财报金融分析项目：`pska-demo-xiaomi-finance-20260805004108`
- 部署 smoke 自动生成项目：`pska-smoke-eidolia-20260805005139`

新增的 `./bootstrap.sh smoke` 已在远端 `http://192.168.31.95:8787` 通过一次基础验收
和一次 `--run-eidolia` 完整验收。验收时“小米财报”数据集 ready，chunk 数为 175；
“海康财报”数据集已存在但仍在 `processing`，chunk 数为 0，因此不作为部署失败。

## 遇到的问题和修正

1. 远端 WSL 到 GitHub/Docker Hub 网络不稳定。

现象：`git fetch`、Docker build 拉依赖、WebUI runtime 依赖安装会超时或长时间卡住。

处理：临时使用开发机代理完成拉取和构建，随后移除 Docker daemon 代理配置。

下次建议：部署前先配置稳定的系统代理、Docker daemon proxy、镜像源或预构建镜像。不要把临时代理 IP 写进 `.env`、Docker systemd drop-in 或 git remote。

2. 私有 `novel` 仓库不适合作为一站式部署依赖。

现象：新机器部署会需要 PAT，不利于演示和复现。

处理：full compose 默认改用 public、中性的 `InfinityCanvas` 仓库。

下次检查：`EIDOLIA_REPO_URL=https://github.com/atom32/InfinityCanvas.git`，git remote URL 不能包含 token。

3. RAGFlow API key 需要先通过 UI 初始化。

现象：`RAGFLOW_API_KEY` 为空时，PSKA 无法使用 live RAGFlow provider。

处理：`bootstrap.sh up` 会在缺 key 时停下并提示先打开 RAGFlow 创建 key。

下次顺序：先 `./bootstrap.sh ragflow-up`，注册 RAGFlow、创建 API key、写回 `.env`，再 `./bootstrap.sh up`。

4. Eidolia 曾报告 `Hermes CLI 未找到：hermes`。

原因：full compose 不应该依赖容器里的 `hermes` CLI。Eidolia 在 demo 路径应通过 Hermes Gateway HTTP 调用 Hermes。

处理：InfinityCanvas/novel 已支持在配置 Gateway 后默认选择 `hermes_gateway`。full compose 显式设置：

```text
NOVEL_AGENT_BACKEND=hermes_gateway
HERMES_GATEWAY_BASE_URL=http://hermes-agent:8642
```

下次验收：`/api/agent/health` 应返回 `backend=hermes_gateway`、`agent_ready=true`。

5. PSKA MCP 不能再走 stdio 或直接绑 CLI。

原因：full compose 里 Hermes Agent 和 PSKA MCP 是两个服务，应该通过内部 HTTP 通信。

处理：Hermes config 生成：

```yaml
mcp_servers:
  pska-essential:
    url: http://pska-mcp:8766/mcp
```

同时 PSKA MCP 服务使用：

```text
pska-essential-mcp --transport streamable-http --host 0.0.0.0 --port 8766 --path /mcp
```

下次验收：`pska-mcp` health 为 healthy；裸 GET `/mcp` 返回 `406` 是正常的 MCP HTTP 行为。

6. Python MCP 依赖版本需要锁定。

现象：干净构建曾拉到 `mcp 2.x`，其中接口布局与当前代码不兼容。

处理：`pyproject.toml` 已将 optional MCP 依赖限制为 `mcp>=1.0.0,<2`。

下次验收：构建日志里应安装 `mcp 1.x`。

7. WebUI sidecar proxy 不是普通裸 curl API。

现象：用脚本直接 POST `/api/extensions/.../sidecar/...` 会得到 `Cross-origin mismatch` 或 `Session expired`。

原因：WebUI sidecar proxy 按浏览器同源请求设计，POST 需要登录 cookie、同源 `Origin/Referer` 和 CSRF token。

处理：新增 `smoke-test.py` 自动按浏览器流程登录、取 CSRF、设置 extension consent 后再调用 sidecar。

下次建议：不要用裸 curl 判断 sidecar 失败。使用：

```bash
./bootstrap.sh smoke
```

8. Eidolia 生成应走异步 run。

现象：直接同步 POST `/api/agent/runs` 可能超过 WebUI sidecar proxy 的 10 秒超时。

处理：UI 和 smoke test 都使用 `async=true` / `asyncRun=true`，先创建 pending 节点，再轮询 run。

下次脚本化测试必须走异步路径。

9. RAGFlow 分块慢不是 PSKA 故障。

现象：海康财报数据集已经上传，但 readiness 为 `processing`，chunk 为 0，队列前还有任务。

处理：先用已 ready 的“小米财报”跑金融分析 demo；海康等 readiness 为 ready 后再跑。

下次演示前必须检查：

```bash
./bootstrap.sh smoke --dataset-name 小米财报 --dataset-name 海康财报
```

10. WSL2 重启后局域网端口需要刷新。

现象：Windows 重启或 WSL 重启后，局域网访问 `8787`/`9222` 可能失效。

处理：使用 `windows/refresh-wsl-portproxy.ps1` 重新生成 portproxy 和防火墙规则。

下次演示前固定检查：Windows 本机和另一台局域网设备都能打开 WebUI 登录页。

## 下次部署推荐顺序

1. 在 WSL 里确认 Docker 可用：

```bash
docker version
docker compose version
```

2. 确认网络能访问 GitHub、Docker Hub/GHCR、PyPI、Hugging Face。弱网环境先配置稳定代理或镜像。

3. 拉取 PSKA-Essential：

```bash
mkdir -p ~/pska-demo
cd ~/pska-demo
git clone https://github.com/atom32/PSKA-Essential.git
cd PSKA-Essential/deploy/full-compose
```

4. 配置 `.env`：

```bash
cp .env.example .env
nano .env
```

必须改：`HERMES_WEBUI_PASSWORD`、`HERMES_GATEWAY_API_KEY`、`WANTED_UID`、`WANTED_GID`。

5. 启动 RAGFlow 并创建 API key：

```bash
./bootstrap.sh ragflow-up
```

6. 将 `RAGFLOW_API_KEY` 写回 `.env`，启动完整系统：

```bash
./bootstrap.sh up
```

7. 跑部署后 smoke：

```bash
./bootstrap.sh smoke
```

如果已经配置 LLM key，并希望验证 Eidolia 生成：

```bash
PSKA_SMOKE_RUN_EIDOLIA=1 ./bootstrap.sh smoke
```

如果有指定演示知识库：

```bash
./bootstrap.sh smoke --dataset-name 小米财报 --dataset-name 海康财报
```

8. Windows 管理员 PowerShell 刷新局域网端口：

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
& "\\wsl.localhost\Ubuntu-24.04\home\<your-linux-user>\pska-demo\PSKA-Essential\deploy\full-compose\windows\refresh-wsl-portproxy.ps1" -Distro Ubuntu-24.04
```

9. 演示前最终确认：

- `http://127.0.0.1:8787` 可登录。
- 局域网 `http://<Windows-LAN-IP>:8787` 可登录。
- `http://<Windows-LAN-IP>:9222` 可打开 RAGFlow。
- WebUI rail 有 Eidolia。
- WebUI chat 有 PSKA chip。
- Eidolia Agent 状态显示 Hermes Gateway ready。
- 目标 RAGFlow 数据集 readiness 为 ready。

## 成功判定

部署可封板为 demo-ready 的最低条件：

- `./bootstrap.sh status` 中 `hermes-webui`、`eidolia`、`pska-api`、`pska-mcp` 为 running/healthy。
- `./bootstrap.sh smoke` 通过。
- 至少一个 RAGFlow 数据集 ready，并能通过 PSKA retrieval probe 返回 context。
- 若要演示创作或金融分析，`PSKA_SMOKE_RUN_EIDOLIA=1 ./bootstrap.sh smoke` 通过。

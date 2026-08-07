# PSKA Full Compose v0

这个目录用于在另一台联网机器上一站式部署当前 PSKA 组件化 Alpha：

```text
RAGFlow upstream compose
  - RAGFlow
  - MySQL
  - Redis
  - MinIO
  - Elasticsearch / Infinity / OpenSearch 等可选 doc engine

PSKA suite compose
  - Embedding / TEI
  - pska-data-init
  - Hermes Agent / Gateway
  - Hermes-WebUI
  - PSKA Product API
  - PSKA MCP installed into Hermes Agent
  - Eidolia
```

Graphiti 不在 v0 主路径里。Memory 和 Review 默认使用 SQLite，并由 `pska-data`
Docker volume 保存。

从零部署请先看 [INSTALL.zh.md](./INSTALL.zh.md)。它按“没有智能体协助”的场景写，
包含 WSL 放到 D 盘、RAGFlow 初始化、局域网端口暴露和重启恢复步骤。
本次远端演示笔记本部署的复盘、踩坑记录和下次检查表见
[DEPLOYMENT_REVIEW_2026-08-05.zh.md](./DEPLOYMENT_REVIEW_2026-08-05.zh.md)。

Embedding 是 v0 的必选基础服务。默认模型是 `BAAI/bge-small-en-v1.5`，这是为了
16GB RAM 的演示笔记本能稳定启动；如果机器内存足够，可以在 `.env` 里把
`EMBEDDING_MODEL_ID` 改成 `BAAI/bge-m3`。默认镜像使用 Hugging Face 的 GHCR
镜像：`ghcr.io/huggingface/text-embeddings-inference:cpu-1.8`。

## 为什么不是一个巨大 compose 文件

RAGFlow 自己已经有复杂的上游 compose、profile 和 `.env`。Full Compose v0 不复制
这些定义，而是由 `bootstrap.sh` 拉取/校验 RAGFlow，然后从 RAGFlow 的 `docker/`
目录启动它自己的 compose。

这样后续更新 RAGFlow 时，不需要在 PSKA 里维护一份过期的 RAGFlow 副本。PSKA 也不会
改写 RAGFlow checkout 里的 `docker/.env`，而是把生成配置写到
`PSKA_SUITE_HOME/ragflow.env` 和 `PSKA_SUITE_HOME/ragflow-pska-full.override.yml`。
RAGFlow 仓库应该保持可 `git pull` 的干净状态。

## 代码来源原则

GitHub 不是运行条件，也不应该是公司内网部署的硬性前提。Full compose 支持三种源码来源：

- `PSKA_FULL_SOURCE_MODE=auto`：默认模式。组件目录缺失时尝试按 URL 拉取；目录已存在时直接使用。
- `PSKA_FULL_SOURCE_MODE=online`：适合公网 GitHub 或公司内网 Git 镜像。可以把
  `EIDOLIA_REPO_URL`、`HERMES_WEBUI_REPO_URL`、`RAGFLOW_REPO_URL` 改成内网镜像地址。
- `PSKA_FULL_SOURCE_MODE=offline`：完全不访问 Git。必须提前把组件源码放到
  `PSKA_SUITE_HOME/repos/InfinityCanvas`、`PSKA_SUITE_HOME/repos/hermes-webui`、
  `PSKA_SUITE_HOME/repos/ragflow`，或在 `.env` 中显式设置对应本地路径。

需要避免的是“拷贝一个带未提交补丁的开发工作目录”。可复现部署应使用 Git tag/commit、
内网 Git 镜像、git bundle、或从干净 baseline 打出的源码包。

如果临时改用私有仓库，才推荐用一次性 `GIT_ASKPASS` 或临时 credential helper 注入 PAT；
不要把 PAT 写入 `origin` URL，也不要提交进 `.env`。部署完成后如使用 Git 源，可确认：

```bash
git -C "$EIDOLIA_REPO" remote -v
git -C "$HERMES_WEBUI_REPO" remote -v
```

URL 应该是普通公网/内网 Git 地址，不能包含 token。离线源码包模式下没有 `.git` 目录也可以，
脚本会按普通源码目录使用。

默认 `EIDOLIA_REPO_URL` 指向中性的 public repo：
`https://github.com/atom32/InfinityCanvas.git`。这个仓库承载 Eidolia 创作工作区能力，
不包含私人 `content/` 或私人 prompt。

## 第一次启动

```bash
cd /path/to/PSKA-Essential/deploy/full-compose
cp .env.example .env
```

编辑 `.env`：

- `HERMES_WEBUI_PASSWORD` 改成真实密码。
- `HERMES_GATEWAY_API_KEY` 改成随机长 token。WebUI 通过它访问 Hermes Gateway。
- `WANTED_UID` / `WANTED_GID` 按 `id -u` / `id -g` 设置。
- 公司内网或离线部署时，把 `PSKA_FULL_SOURCE_MODE` 改成 `offline`，并提前放好组件源码。
- 填你要用的 Hermes 模型环境变量，例如 `DEEPSEEK_API_KEY`。
- 先留空 `RAGFLOW_API_KEY`。
- 保持 `EMBEDDING_ENABLED=1`。默认会启动本地 TEI embedding 服务。
- `RAGFLOW_TEI_BASE_URL` 可以留空，脚本会让 RAGFlow 通过 Docker 私有网络访问
  `http://pska-embedding:80`，不需要把 embedding 暴露到局域网。
- 弱网或公司网络需要代理/镜像源时，优先在 `.env` 配置 `HTTP_PROXY`、
  `HTTPS_PROXY`、`NO_PROXY`、`BUILD_APT_PROXY`、`DEBIAN_APT_MIRROR`、
  `DEBIAN_SECURITY_APT_MIRROR`、`NPM_CONFIG_REGISTRY`、`PIP_INDEX_URL`、
  `UV_DEFAULT_INDEX`，不要手改 Dockerfile 或 git remote。Debian apt 镜像建议使用
  `http://...`，避免 slim 基础镜像安装证书包前无法访问 HTTPS 源。

可用下面命令生成 Gateway token：

```bash
openssl rand -hex 32
```

先启动 RAGFlow：

```bash
./bootstrap.sh ragflow-up
```

这个命令会先启动本地 embedding 容器，再启动 RAGFlow upstream compose。

打开 RAGFlow：

```text
http://127.0.0.1:8080
```

完成 RAGFlow 一次性初始化：

- 创建用户/登录；
- 配置 LLM provider；
- embedding 使用内置模型：`BAAI/bge-small-en-v1.5@Builtin`，除非你在 `.env`
  里换了 `EMBEDDING_MODEL_ID`；
- 创建 API key；
- 把 API key 写回 `.env` 的 `RAGFLOW_API_KEY`。

然后启动整套 PSKA：

```bash
./bootstrap.sh up
```

默认 `PSKA_FULL_BUILD=auto`。需要强制按当前源码重建镜像时用
`PSKA_FULL_BUILD=1 ./bootstrap.sh up`；弱网环境只重启已有镜像时用
`PSKA_FULL_BUILD=0 ./bootstrap.sh up`。

打开主入口：

```text
http://127.0.0.1:8787
```

如果部署在 WSL2 里，Windows 本机浏览器通常可以访问 `localhost:8787`，但局域网其他设备
访问 `http://<Windows-IP>:8787` 可能会超时。演示时如果需要从另一台设备访问，请在
Windows 管理员 PowerShell 里把端口转发到当前 WSL IP，并放通防火墙：

```powershell
$wslIp = (wsl hostname -I).Trim().Split(" ")[0]
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=8787 connectaddress=$wslIp connectport=8787
New-NetFirewallRule -DisplayName "PSKA Demo WebUI 8787" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8787
```

如果也要让观众直接打开 RAGFlow UI，同理转发 `8080`。不要转发 embedding 端口；它应保持
`127.0.0.1:6380` 或容器私有网络访问。

仓库也提供了一个管理员 PowerShell 辅助脚本：

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
& "\\wsl.localhost\Ubuntu-24.04\home\<linux-user>\pska-demo\PSKA-Essential\deploy\full-compose\windows\refresh-wsl-portproxy.ps1" -Distro Ubuntu-24.04
```

默认会暴露 `8787`，并把 Windows `9222` 转发到 WSL 内 RAGFlow Web `8080`。

## 服务分工

对外入口：

- `Hermes-WebUI`: `8787`
- `RAGFlow Web`: 默认 `8080`

本机调试入口：

- `Embedding / TEI`: `127.0.0.1:6380`
- `Hermes Gateway`: `127.0.0.1:8642`
- `RAGFlow API`: `127.0.0.1:9380`

不直接暴露：

- `PSKA Product API`: WebUI 容器视角的 `127.0.0.1:8765`
- `PSKA MCP`: Docker 内网 `http://pska-mcp:8766/mcp`
- `Eidolia`: WebUI 容器视角的 `127.0.0.1:8797`

`pska-data-init` 是一次性容器，只负责把共享的 `pska-data` volume chown 到
`WANTED_UID:WANTED_GID`。这样 PSKA MCP 和 PSKA Product API 能同时
读写 SQLite Memory / Review。

## 已打通的路径

```text
WebUI -> Hermes Agent -> PSKA MCP HTTP -> RAGFlow
WebUI chat -> Hermes Gateway API -> Hermes Agent -> PSKA MCP HTTP
WebUI -> PSKA chip extension -> PSKA Product API -> RAGFlow
WebUI -> Eidolia rail extension -> Eidolia
Eidolia -> Ask PSKA evidence -> PSKA Product API -> RAGFlow
Eidolia -> Hermes Gateway -> Hermes Agent -> PSKA MCP HTTP
PSKA API / MCP -> SQLite Memory + SQLite Review
RAGFlow -> PSKA embedding container -> local TEI model
```

## v0 暂不承诺

- 不自动生成 RAGFlow API key；这一步仍然需要进 RAGFlow 做一次初始化。
- RAGFlow 账号/API key 也可以通过 RAGFlow API 初始化，但 v0 文档仍以 UI 手工路径为准。
- 不自动配置 RAGFlow 的外部 LLM provider；不同模型供应商差异较大。
- Eidolia 的普通生成路径走 Hermes Gateway runs API；`agentic_tools` 里依赖
  Eidolia 自己 novel-local MCP 的深度工具循环仍不作为 v0 主路径。
- 不启动 Graphiti。

## 常用命令

```bash
./bootstrap.sh init
./bootstrap.sh embedding-up
./bootstrap.sh ragflow-up
./bootstrap.sh ragflow-model-sync
./bootstrap.sh up
./bootstrap.sh sidecars
PSKA_FULL_BUILD=1 ./bootstrap.sh up
./bootstrap.sh status
./bootstrap.sh smoke
PSKA_SMOKE_RUN_EIDOLIA=1 ./bootstrap.sh smoke
./bootstrap.sh logs
./bootstrap.sh down
```

`down` 会停止服务但保留 Docker volume。清空数据请手动删除对应 volume。

`sidecars` 用于修复 WebUI extension 访问 PSKA Product API / Eidolia 的 loopback 链路。
`pska-api` 和 `eidolia` 使用 `network_mode: service:hermes-webui`，所以 WebUI 被重启
或重建后，这两个 sidecar 容器要重新挂回当前 WebUI 网络命名空间。出现
`/api/extensions/.../sidecar/... 502` 时，优先执行：

```bash
./bootstrap.sh sidecars
```

不要只看 `docker compose ps` 的 healthy 状态；正确检查点是从 `hermes-webui` 容器内部
访问 `127.0.0.1:8765` 和 `127.0.0.1:8797`。`./bootstrap.sh sidecars` 会自动做这个检查。

`smoke` 会按真实浏览器路径登录 WebUI，确认 extension sidecar、PSKA Product API、
Eidolia Hermes Gateway backend、数据集列表、RAGFlow Builtin embedding 生成配置、
Eidolia ZIP 导入/导出依赖、旧 `tenant_llm` 兼容表和新 `tenant_model_*` UI 投影表可用。设置
`PSKA_SMOKE_RUN_EIDOLIA=1` 后会额外创建一个很小的 Eidolia 项目，
通过 Hermes Gateway 异步生成一个 thought 节点。

如果 RAGFlow 的模型配置页找不到内置 embedding，先更新到包含本段的版本，然后重新生成
运行配置并重启 RAGFlow：

```bash
./bootstrap.sh init
./bootstrap.sh ragflow-up
./bootstrap.sh ragflow-model-sync
```

`ragflow-model-sync` 会同步三层状态：`service_conf.yaml.template` 的 Builtin TEI 配置、
RAGFlow 旧模型表，以及 v0.26 模型设置页使用的新 `tenant_model_provider` /
`tenant_model_instance` / `tenant_model` 表。同步后刷新
`http://<server>:8080/user-setting/model`，Embedding 下拉应出现
`BAAI/bge-small-en-v1.5`。

生成的 `.runtime/ragflow-service_conf.yaml.template` 中应包含：

```yaml
user_default_llm:
  default_models:
    embedding_model:
      name: 'BAAI/bge-small-en-v1.5'
      factory: 'Builtin'
      api_key: 'xxx'
      base_url: 'http://pska-embedding:80'
```

## 运行态目录

默认在：

```text
deploy/full-compose/.runtime
```

包含：

- `repos/InfinityCanvas`
- `repos/hermes-webui`
- `repos/ragflow`
- `hermes-home/config.yaml`
- `hermes-home/pska.env`
- `ragflow.env`
- `ragflow-pska-full.override.yml`
- `ragflow-service_conf.yaml.template`
- `workspace/`

`bootstrap.sh` 会按当前模板更新 `hermes-home/config.yaml`，旧文件会备份为
`config.yaml.bak-*`。如果你临时手改了 Hermes 配置并希望脚本不要覆盖，设置
`PSKA_FULL_KEEP_HERMES_CONFIG=1`。

`bootstrap.sh` 会预写 WebUI extension consent：

```text
pska-mini -> http://127.0.0.1:8765
eidolia -> http://127.0.0.1:8797
```

## Windows 快捷入口

WSL 演示机可以使用 `windows/` 目录下的批处理文件，不必每次进 WSL 手动执行。建议把整个
`windows/` 文件夹复制到桌面或固定位置，因为这些脚本依赖同目录下的 `_pska-wsl-run.cmd`
helper：

- `pska-start.cmd`：启动全套服务并显示状态。
- `pska-stop.cmd`：停止服务，保留 Docker volume。
- `pska-status.cmd`：查看服务状态。
- `pska-smoke.cmd`：运行基础 smoke test。
- `pska-fix-sidecars.cmd`：WebUI 能打开但 PSKA chip / Eidolia 报 502 时使用。
- `pska-refresh-portproxy.cmd`：刷新 Windows 到 WSL 的端口转发，需要管理员终端。
- `pska-stop-and-shutdown-wsl.cmd`：先停服务，再执行 `wsl --shutdown`。

默认假设 WSL distro 是 `Ubuntu-24.04`，项目路径是
`~/pska-demo/PSKA-Essential/deploy/full-compose`。如果不同，复制
`windows/pska-demo-env.cmd.example` 为 `windows/pska-demo-env.cmd` 后修改。

WSL 不会因为关闭终端就一定自动停止。只要 Docker Desktop、compose 容器或后台服务还在，
WSL2 VM 可能继续运行。演示结束后建议先运行 `pska-stop.cmd`；需要明确释放 WSL 时再运行
`pska-stop-and-shutdown-wsl.cmd`。

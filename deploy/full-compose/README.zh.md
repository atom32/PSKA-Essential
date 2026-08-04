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

部署机应该从 GitHub 拉取组件仓库，而不是从开发机拷贝工作目录。这样才能验证一站式部署
和后续升级路径。

如果组件仓库需要私有访问权限，推荐用一次性 `GIT_ASKPASS` 或临时 credential helper
注入 PAT；不要把 PAT 写入 `origin` URL，也不要提交进 `.env`。部署完成后确认：

```bash
git -C "$EIDOLIA_REPO" remote -v
git -C "$HERMES_WEBUI_REPO" remote -v
```

URL 应该仍是普通 `https://github.com/...`，不能包含 token。

当前 `EIDOLIA_REPO_URL` 仍指向开发期的 `atom32/novel`。对外演示前，建议把 Eidolia
工作区能力整理成一个中性的 public repo，再把 `.env` 里的 `EIDOLIA_REPO_URL` 改到新仓库。

## 第一次启动

```bash
cd /path/to/PSKA-Essential/deploy/full-compose
cp .env.example .env
```

编辑 `.env`：

- `HERMES_WEBUI_PASSWORD` 改成真实密码。
- `HERMES_GATEWAY_API_KEY` 改成随机长 token。WebUI 通过它访问 Hermes Gateway。
- `WANTED_UID` / `WANTED_GID` 按 `id -u` / `id -g` 设置。
- 填你要用的 Hermes 模型环境变量，例如 `DEEPSEEK_API_KEY`。
- 先留空 `RAGFLOW_API_KEY`。
- 保持 `EMBEDDING_ENABLED=1`。默认会启动本地 TEI embedding 服务。
- `RAGFLOW_TEI_BASE_URL` 可以留空，脚本会按 `EMBEDDING_HOST_PORT` 自动写成
  `http://host.docker.internal:<port>`。

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

打开主入口：

```text
http://<机器IP>:8787
```

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
- `Eidolia`: WebUI 容器视角的 `127.0.0.1:8797`

`pska-data-init` 是一次性容器，只负责把共享的 `pska-data` volume chown 到
`WANTED_UID:WANTED_GID`。这样 Hermes Agent 内的 PSKA MCP 和 PSKA Product API 能同时
读写 SQLite Memory / Review。

## 已打通的路径

```text
WebUI -> Hermes Agent -> PSKA MCP -> RAGFlow
WebUI chat -> Hermes Gateway API -> Hermes Agent -> PSKA MCP
WebUI -> PSKA chip extension -> PSKA Product API -> RAGFlow
WebUI -> Eidolia rail extension -> Eidolia
Eidolia -> Ask PSKA evidence -> PSKA Product API -> RAGFlow
PSKA API / MCP -> SQLite Memory + SQLite Review
RAGFlow -> PSKA embedding container -> local TEI model
```

## v0 暂不承诺

- 不自动生成 RAGFlow API key；这一步仍然需要进 RAGFlow 做一次初始化。
- 不自动配置 RAGFlow 的外部 LLM provider；不同模型供应商差异较大。
- Eidolia 的 Hermes CLI 生成路径仍不是容器内完整闭环；Eidolia 的 Ask PSKA
  evidence 路径已容器化。
- 不启动 Graphiti。

## 常用命令

```bash
./bootstrap.sh init
./bootstrap.sh embedding-up
./bootstrap.sh ragflow-up
./bootstrap.sh up
./bootstrap.sh status
./bootstrap.sh logs
./bootstrap.sh down
```

`down` 会停止服务但保留 Docker volume。清空数据请手动删除对应 volume。

## 运行态目录

默认在：

```text
deploy/full-compose/.runtime
```

包含：

- `repos/novel`
- `repos/hermes-webui`
- `repos/ragflow`
- `hermes-home/config.yaml`
- `hermes-home/pska.env`
- `ragflow.env`
- `ragflow-pska-full.override.yml`
- `ragflow-service_conf.yaml.template`
- `workspace/`

`bootstrap.sh` 会预写 WebUI extension consent：

```text
pska-mini -> http://127.0.0.1:8765
eidolia -> http://127.0.0.1:8797
```

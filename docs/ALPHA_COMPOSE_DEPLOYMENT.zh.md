# PSKA Alpha Compose Deployment

这个 compose 是 Alpha A：把 Hermes-WebUI、PSKA Product API、Eidolia 放进同一个本地部署单元，RAGFlow 仍然作为外部成熟服务接入。

## 能力边界

已覆盖：

- Hermes-WebUI 是唯一对外入口，默认发布 `8787`。
- PSKA-mini extension 通过 WebUI sidecar proxy 调用 PSKA Product API。
- Eidolia rail extension 通过 WebUI sidecar proxy 打开 Eidolia。
- Eidolia 的 Ask PSKA / evidence retrieval 调用同一个 PSKA Product API。
- PSKA 的 SQLite review 和 SQLite memory 存在 Docker volume `pska-data`。

暂不伪装覆盖：

- RAGFlow 不在这个 compose 里启动；默认用 `RAGFLOW_BASE_URL=http://host.docker.internal:9380` 接外部 RAGFlow。
- Hermes Agent / Hermes CLI / PSKA MCP 的容器内闭环是 Alpha B；当前 compose A 主要保证 WebUI 扩展和 Product API 路径。
- Eidolia 里需要 Hermes CLI 的生成能力，仍然依赖后续把 Hermes runtime 放进容器或挂接到宿主机。

## 为什么使用共享网络命名空间

Hermes-WebUI 的 extension sidecar 安全模型只接受 loopback origin，例如 `http://127.0.0.1:8765`。它不会接受 `http://pska-api:8765` 这种 Docker service DNS。

所以 compose 让 `pska-api` 和 `eidolia` 使用：

```yaml
network_mode: "service:hermes-webui"
```

这样在 WebUI 容器视角里：

- PSKA API 是 `http://127.0.0.1:8765`
- Eidolia 是 `http://127.0.0.1:8797`

宿主机和局域网只看到 WebUI 的 `8787`。PSKA API 和 Eidolia 不直接发布端口。

`host.docker.internal` 的 host 映射声明在 `hermes-webui` 主服务上；companion 容器共享该服务的网络命名空间，不能再单独声明 `extra_hosts`。

WebUI 的 extension root 使用 Docker named volume，`extensions.json` 和两个 extension 源码目录只读挂载进去。这样 WebUI 即使写 extension state，也不会污染源码仓库。

## 启动

```bash
cd /Users/xudawei/PSKA-Essential/deploy/alpha-compose
cp .env.example .env
```

编辑 `.env`：

- `HERMES_WEBUI_PASSWORD` 改成你的 WebUI 密码。
- `WANTED_UID` / `WANTED_GID` 按 `id -u` / `id -g` 设置，避免容器读写 `~/.hermes` 出现权限问题。
- `RAGFLOW_API_KEY` 填 RAGFlow API key。
- 如果 RAGFlow 不在本机 Docker Desktop host 上，改 `RAGFLOW_BASE_URL`。
- 如果 WebUI 镜像构建时 Debian apt 源偶发 502，可以重试，或设置 `BUILD_APT_PROXY`。

启动：

```bash
docker compose up -d --build
docker compose ps
```

打开：

```text
http://<机器IP>:8787
```

第一次进入 Docker WebUI 状态目录时，可能需要：

```text
Settings -> Extensions -> Approve proxy consent
```

分别给 `pska-mini` 和 `eidolia` 批准 sidecar proxy。这是 WebUI 的安全机制。

## 健康检查

```bash
docker compose ps
docker compose logs -f pska-api
docker compose logs -f eidolia
docker compose logs -f hermes-webui
```

在 WebUI 里检查：

- rail 上能看到 Eidolia 按钮；
- composer 里能看到 PSKA chip；
- Settings -> Extensions 里 `pska-mini` 和 `eidolia` sidecar 为 healthy；
- PSKA chip 的 dataset/scope 能读取 RAGFlow 数据集。

## Boot-only fake 模式

只为了检查 compose 和 UI 线路时，可以显式 fake：

```env
PSKA_DEV_FAKE=1
PSKA_RETRIEVAL_PROVIDER=fake
PSKA_KB_PROVIDER=fake
PSKA_MEMORY_PROVIDER=fake
RAGFLOW_API_KEY=
```

这不能作为 live retrieval 证明。正式 demo 仍然应该使用 RAGFlow。

## 停止

```bash
docker compose down
```

保留 memory/review/project 数据：

```bash
docker compose down
```

清空 Alpha 数据：

```bash
docker compose down -v
```

## 下一步：Alpha B

Alpha B 要补的是运行时闭环：

- Hermes Agent 容器或 gateway daemon；
- WebUI 内 Hermes profile 能发现 PSKA MCP；
- Eidolia 的 generation path 能调用 Hermes，而不是只做 PSKA evidence retrieval；
- scheduled tasks / digest runner 走 Hermes gateway，而不是 WebUI 单容器假定。

# PSKA Full Compose 手工部署手顺

这份文档的目标是：没有智能体协助时，也能在一台新的 Windows 笔记本上部署并演示
PSKA full compose。

默认目标形态：

```text
Windows 11
  -> WSL2 Ubuntu 24.04
    -> Docker Desktop WSL integration
      -> PSKA Full Compose
        - Hermes-WebUI
        - Hermes Agent / Gateway
        - PSKA-Essential API + MCP
        - InfinityCanvas / Eidolia
        - RAGFlow
        - local TEI embedding
        - SQLite memory / review
```

对局域网只建议暴露两个端口：

- `8787`: Hermes-WebUI 主入口
- `9222`: RAGFlow Web UI，Windows 转发到 WSL 内部 `8080`

不要把 embedding、数据库、MinIO、Redis、Elasticsearch、RAGFlow API 直接暴露给局域网。

## 1. Windows 准备

安装：

- Windows 11
- WSL2
- Docker Desktop，并启用目标 WSL distro 的 integration
- Git for Windows 可选；PSKA 代码主要在 WSL 里用 Linux git

推荐把 WSL distro 放到 D 盘，避免 Docker 镜像、RAGFlow 数据和模型缓存挤占 C 盘。
同时检查 Docker Desktop 的数据盘位置；只移动 Ubuntu distro 不一定移动
`docker-desktop-data`。在 Docker Desktop Settings -> Resources -> Advanced 里，把
Disk image location 也放到 D 盘空间充足的位置。

如果已经装好 Ubuntu，可以这样迁移到 D 盘。先在管理员 PowerShell 里查看 distro 名称：

```powershell
wsl -l -v
```

假设名称是 `Ubuntu-24.04`：

```powershell
wsl --shutdown
mkdir D:\WSL
wsl --export Ubuntu-24.04 D:\WSL\Ubuntu-24.04.tar
wsl --unregister Ubuntu-24.04
wsl --import Ubuntu-24.04 D:\WSL\Ubuntu-24.04 D:\WSL\Ubuntu-24.04.tar --version 2
```

注意：`wsl --unregister` 会删除原 distro。先确认 `wsl --export` 已经成功生成 tar，
再执行 unregister。

导入后的默认用户可能变成 `root`。进入 WSL 后把默认用户写回去：

```powershell
wsl -d Ubuntu-24.04 -u root
```

在 WSL 里执行：

```bash
printf "[user]\ndefault=<your-linux-user>\n" > /etc/wsl.conf
exit
```

回到 PowerShell：

```powershell
wsl --terminate Ubuntu-24.04
wsl -d Ubuntu-24.04
```

确认默认用户正确后，再删除临时 tar：

```powershell
del D:\WSL\Ubuntu-24.04.tar
```

## 2. WSL 基础依赖

在 WSL Ubuntu 里执行：

```bash
sudo apt update
sudo apt install -y git curl ca-certificates jq openssl python3 python3-venv build-essential
docker version
docker compose version
```

如果 `docker version` 不能连接 Docker daemon，打开 Docker Desktop：

1. Settings -> Resources -> WSL Integration
2. 启用当前 Ubuntu distro
3. 回到 WSL 重新执行 `docker version`

## 3. 拉取 PSKA-Essential

部署机应该从 GitHub 拉取，不从开发机拷贝目录：

```bash
mkdir -p ~/pska-demo
cd ~/pska-demo
git clone https://github.com/atom32/PSKA-Essential.git
cd PSKA-Essential/deploy/full-compose
```

full compose 会自动拉取这些组件：

- `https://github.com/atom32/InfinityCanvas.git`
- `https://github.com/nesquena/hermes-webui.git`
- `https://github.com/infiniflow/ragflow.git`

默认不需要 PAT。不要把 PAT 写进 git remote URL 或 `.env`。

## 4. 创建 .env

```bash
cp .env.example .env
nano .env
```

必须修改：

```bash
HERMES_WEBUI_PASSWORD=<your-webui-password>
HERMES_GATEWAY_API_KEY=<random-long-token>
WANTED_UID=<id -u>
WANTED_GID=<id -g>
RAGFLOW_API_KEY=
```

生成 gateway token：

```bash
openssl rand -hex 32
```

查看 UID/GID：

```bash
id -u
id -g
```

LLM API key 有两种方式：

- demo 推荐：先留空，在 Hermes-WebUI 第一次打开时按引导填写。
- 可复现部署：写入 `.env`，例如 `DEEPSEEK_API_KEY`、`OPENAI_API_KEY`。

`RAGFLOW_API_KEY` 先留空，等 RAGFlow 初始化后再填。

## 5. 初始化并启动 RAGFlow

先生成运行态配置并启动 embedding + RAGFlow：

```bash
./bootstrap.sh ragflow-up
```

这个命令会：

- 拉取 InfinityCanvas、Hermes-WebUI、RAGFlow 仓库
- 生成 Hermes/PSKA/RAGFlow 运行配置
- 启动本地 TEI embedding
- 启动 RAGFlow upstream compose

打开 RAGFlow：

```text
http://127.0.0.1:8080
```

在 RAGFlow UI 里完成：

1. 注册或登录一个账号。
2. 创建 API key。
3. 如果需要 RAGFlow 自己生成回答，配置 LLM provider。
4. embedding 使用 full compose 接入的本地模型；默认模型是
   `BAAI/bge-small-en-v1.5`。

把 RAGFlow API key 写回 `.env`：

```bash
nano .env
```

```bash
RAGFLOW_API_KEY=<ragflow-api-key>
```

## 6. 启动整套 PSKA

```bash
./bootstrap.sh up
```

查看状态：

```bash
./bootstrap.sh status
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

Windows 本机浏览器打开：

```text
http://127.0.0.1:8787
```

如果 WebUI 出现 LLM API key 引导，按页面填写即可。这个 key 属于 Hermes 运行态配置，
不需要提交到 git。

## 7. 局域网访问

WSL2 重启后 IP 可能变化，所以 Windows `portproxy` 需要刷新。仓库提供了脚本：

```text
deploy/full-compose/windows/refresh-wsl-portproxy.ps1
```

在管理员 PowerShell 里运行。把 distro 名称和 Linux 用户名替换成自己的：

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
& "\\wsl.localhost\Ubuntu-24.04\home\<your-linux-user>\pska-demo\PSKA-Essential\deploy\full-compose\windows\refresh-wsl-portproxy.ps1" -Distro Ubuntu-24.04
```

如果 `\\wsl.localhost` 不可用，可以试：

```powershell
& "\\wsl$\Ubuntu-24.04\home\<your-linux-user>\pska-demo\PSKA-Essential\deploy\full-compose\windows\refresh-wsl-portproxy.ps1" -Distro Ubuntu-24.04
```

默认脚本会配置：

```text
0.0.0.0:8787 -> WSL:<8787>
0.0.0.0:9222 -> WSL:<8080>
```

防火墙只允许 `LocalSubnet` 来源。

查看 Windows 局域网 IP：

```powershell
ipconfig
```

其他设备访问：

```text
http://<Windows-LAN-IP>:8787
http://<Windows-LAN-IP>:9222
```

## 8. 最小验收

在 WSL 里：

```bash
cd ~/pska-demo/PSKA-Essential/deploy/full-compose
./bootstrap.sh status
curl -sS -o /dev/null -w "webui:%{http_code}\n" http://127.0.0.1:8787/
docker exec pska-full-hermes-webui-1 curl -fsS http://127.0.0.1:8765/api/health | jq .
```

`webui` 返回 `302` 是正常的，表示跳转到登录流程。

在 Windows 或其他局域网机器：

```text
Hermes-WebUI 能打开登录页
RAGFlow 能打开登录页
```

进入 WebUI 后检查：

- rail 里有 Eidolia。
- chat 页面能看到 PSKA chip。
- Eidolia 能打开默认空项目。
- Eidolia 左侧 Agent 状态显示 Hermes Gateway 就绪，而不是 Hermes CLI 缺失。
- Eidolia 的 Ask PSKA evidence 能调用 PSKA。
- WebUI chat 在 PSKA chip 开启时，Hermes 可以按 PSKA skill/MCP 使用 RAGFlow 证据。

## 9. 重启后的恢复

每次重启 Windows 笔记本后：

1. 打开 Docker Desktop，等它启动完成。
2. 打开 WSL。
3. 在 WSL 执行：

```bash
cd ~/pska-demo/PSKA-Essential/deploy/full-compose
./bootstrap.sh up
./bootstrap.sh status
```

4. 在管理员 PowerShell 执行 `refresh-wsl-portproxy.ps1`。
5. 打开 `http://127.0.0.1:8787` 或局域网 `http://<Windows-LAN-IP>:8787`。

## 10. 更新代码

保持 main/master 干净，不要在部署机创建新分支：

```bash
cd ~/pska-demo/PSKA-Essential
git status --short --branch
git pull --ff-only
```

如果要同步组件仓库：

```bash
cd ~/pska-demo/PSKA-Essential/deploy/full-compose
PSKA_FULL_UPDATE_REPOS=1 ./bootstrap.sh init
./bootstrap.sh up
```

确认组件仓库没有脏改：

```bash
git -C .runtime/repos/InfinityCanvas status --short --branch
git -C .runtime/repos/hermes-webui status --short --branch
git -C .runtime/repos/ragflow status --short --branch
```

## 11. 常见问题

`./bootstrap.sh up` 提示 `RAGFLOW_API_KEY is empty`：

先打开 RAGFlow 创建 API key，写回 `.env`，再重新运行。

局域网无法访问 `8787` 或 `9222`：

WSL IP 变了。重新运行 `refresh-wsl-portproxy.ps1`。

WebUI 能打开但聊天提示没有模型：

在 WebUI 引导里填写 LLM API key，或把 key 写入 `.env` 后重启：

```bash
./bootstrap.sh up
```

RAGFlow 解析慢或卡住：

先确认 embedding 容器启动：

```bash
docker ps | grep pska-full-embedding
curl -fsS http://127.0.0.1:6380/health
```

16GB RAM 机器不要轻易切到 `BAAI/bge-m3`，默认 `BAAI/bge-small-en-v1.5` 更稳。

需要停止服务但保留数据：

```bash
./bootstrap.sh down
```

需要彻底清空数据时，再手动删除 Docker volume；不要在没有备份时这样做。

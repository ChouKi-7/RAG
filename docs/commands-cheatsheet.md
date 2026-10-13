# rag-starter 常用命令速查

> 写给：记不住那一长串命令的自己。
> 用途：要做某个操作时，直接来这里复制粘贴，不用再翻聊天记录找。

---

## 一、本地开发

```bash
# 激活虚拟环境（每次开新终端都要做）
source venv/bin/activate

# 安装/更新本地依赖
pip install -r requirements.txt

# 运行 CLI 版（命令行问答）
python main.py

# 运行 Web 版（本地浏览器测试，不经过 Docker）
streamlit run app.py
```

---

## 二、本地 Docker 测试

```bash
# 构建镜像（本机架构，仅用于本地测试，不能直接用于部署！）
docker build -t rag-starter .

# 本地运行容器
docker run -p 8501:8501 --env-file .env -e EMBEDDING_PROVIDER=google rag-starter
# 然后浏览器打开 http://localhost:8501（不是 0.0.0.0）

# 查看正在运行的容器
docker ps

# 查看所有容器（包括已停止的）
docker ps -a

# 停止容器（Ctrl+C 失灵时用这个）
docker stop <容器ID>

# 清理所有已停止的容器（镜像显示"in use"删不掉时用）
docker container prune

# 查看本地镜像列表
docker images
```

---

## 三、推送镜像到 Docker Hub（部署 / 更新代码后都要做这一步）

```bash
docker login   # 只需要登录一次，之后会记住

# 关键：必须用 buildx 构建 linux/amd64 架构，否则 Azure 会报架构不匹配的错
docker buildx build --platform linux/amd64 -t <DockerHub用户名>/rag-starter:latest --push .
```

**不要用** `docker build` + `docker push` 这套普通流程来部署——本机是 Apple Silicon（arm64），普通构建出来的镜像架构不对，Azure Container Apps 跑不起来。

---

## 四、Azure 初始设置（一次性操作，正常不会再用到）

```bash
# 装 Azure CLI
brew install azure-cli
az login

# 装 Container Apps 扩展、注册服务提供者（只需一次）
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights

# 创建资源组
az group create --name rag-starter-rg --location japaneast

# 创建 Container Apps 环境
az containerapp env create \
  --name rag-starter-env \
  --resource-group rag-starter-rg \
  --location japaneast

# 首次创建 Container App（只在第一次部署时用，之后改代码用「五、更新部署」那套）
az containerapp create \
  --name rag-starter-app \
  --resource-group rag-starter-rg \
  --environment rag-starter-env \
  --image <DockerHub用户名>/rag-starter:latest \
  --target-port 8501 \
  --ingress external \
  --secrets google-api-key=<真实GOOGLE_API_KEY> \
  --env-vars GOOGLE_API_KEY=secretref:google-api-key EMBEDDING_PROVIDER=google \
  --min-replicas 0 --max-replicas 1
```

---

## 五、改完代码后，更新部署（最常用的流程）

```bash
# 1. 改代码

# 2. 重新构建 + 推送镜像
docker buildx build --platform linux/amd64 -t <DockerHub用户名>/rag-starter:latest --push .

# 3. 让 Azure 拉取新镜像（注意是 update，不是 create）
az containerapp update --name rag-starter-app --resource-group rag-starter-rg --image <DockerHub用户名>/rag-starter:latest
```

---

## 六、日常查看 / 管理

```bash
# 查看应用网址
az containerapp show --name rag-starter-app --resource-group rag-starter-rg --query properties.configuration.ingress.fqdn -o tsv

# 查看运行状态
az containerapp show --name rag-starter-app --resource-group rag-starter-rg --query properties.runningStatus

# 实时查看日志（Ctrl+C 退出查看，不影响应用本身运行）
az containerapp logs show --name rag-starter-app --resource-group rag-starter-rg --follow

# 查看当前有几个实例在跑（没人访问时应该是空列表，说明缩到 0 了）
az containerapp replica list --name rag-starter-app --resource-group rag-starter-rg
```

网页版：Azure Portal(portal.azure.com) → 搜索 `rag-starter-app` → 左侧「监视」→「Log stream」，效果跟上面命令行一样，不用敲命令。

---

## 七、清理 / 不想要了

```bash
# 一次性删除这个项目在 Azure 上的所有资源（资源组、环境、应用全部删干净）
az group delete --name rag-starter-rg

# 清理本地没用的 Docker 容器/镜像
docker container prune
docker image prune
```

---

## 八、其他常用命令（目前用不到，但以后排查问题/管理时会用到）

### Docker

```bash
# 删除指定镜像（先确保没有容器在用它，见第二节 prune）
docker rmi <镜像名或ID>

# 钻进一个正在运行的容器内部，像进了一个远程终端一样（排查问题用）
docker exec -it <容器ID> sh

# 查看某个容器的日志（不用 -it 进去，直接看输出）
docker logs <容器ID>
docker logs -f <容器ID>   # -f 持续追踪，像 tail -f

# 查看容器的详细配置信息（JSON格式，端口映射、环境变量等都在里面）
docker inspect <容器ID>

# 实时查看容器的资源占用（CPU、内存），类似 Mac 的活动监视器
docker stats

# 查看 Docker 占了多少硬盘空间（镜像、容器、缓存分别多大）
docker system df

# 一次性清理所有没用的东西（镜像、容器、网络、构建缓存），彻底释放空间
docker system prune -a
```

### Azure

```bash
# 查看当前登录的是哪个账号/订阅
az account show

# 列出这个账号下所有的资源组（不止 rag-starter-rg 这一个）
az group list -o table

# 列出这个账号下所有的 Container App（如果以后做了别的项目）
az containerapp list -o table

# 查看某个 Container App 的历史版本（每次 update 都会生成一条新记录）
az containerapp revision list --name rag-starter-app --resource-group rag-starter-rg -o table

# 只删除这一个应用，不删整个资源组/环境（比 az group delete 更精细）
az containerapp delete --name rag-starter-app --resource-group rag-starter-rg

# 退出登录（换账号或者在别人电脑上用完要清理时）
az logout
```

**查费用**：Azure CLI 查费用的命令比较繁琐，不推荐背命令，直接去 Azure Portal 网页 → 搜索「成本管理」（Cost Management）→ 选对应的订阅，图表化看得更清楚。

---

*这份速查表由 Claude 根据 2026-10-13 之前的部署过程整理，命令参数以当时验证通过的为准，如果 Azure CLI 以后有重大版本变化，建议对照当前 `az containerapp --help` 输出核对。*

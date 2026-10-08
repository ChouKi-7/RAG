# rag-starter 部署到 Azure 笔记

> 写给：刚开始学部署、还不熟悉 Docker / Azure 概念的自己。
> 用途：忘了部署到哪一步、或者为什么要做某一步时，回来看这篇。

---

## 一、这次要做什么（目标）

把现在这个本地跑的 RAG 项目，变成一个**别人也能通过网址访问的网页应用**，部署在 Azure（微软的云平台）上。

整体思路分两段：
1. **本地**：把项目打包成一个"容器镜像"（Docker image）——相当于把"代码 + 运行环境 + 依赖库"打包成一个可以在任何机器上原样运行的箱子
2. **云端**：把这个箱子推到 Azure 上，让 Azure 24 小时运行它，并给它分配一个网址

---

## 二、几个关键概念（新手向解释）

| 术语 | 是什么 | 类比 |
|---|---|---|
| **Docker** | 一个"打包+运行容器"的工具 | 集装箱的打包机 |
| **Dockerfile** | 一份"打包说明书"，写明"用什么底座、装哪些东西、怎么启动" | 装箱清单 |
| **镜像（image）** | 按照 Dockerfile 打包出来的"箱子"，是静态的文件 | 打包好、还没拆封的集装箱 |
| **容器（container）** | 镜像被"运行起来"之后的状态 | 集装箱被打开、里面的工厂在实际运转 |
| **ACR（Azure Container Registry）** | Azure 提供的"镜像仓库"，存放你的镜像 | 集装箱码头的仓库 |
| **App Service / Container Apps** | Azure 提供的"运行容器"的服务，负责 24 小时跑着你的镜像并给个网址 | 真正运转集装箱里工厂的厂房 |

**本地测试 vs 云端部署的区别**：
- 本地用 `docker build` + `docker run` 是为了"打包测试一下箱子能不能正常运作"，这一步**不花钱**，在你自己电脑上
- 真正的"部署"是把这个箱子推到 ACR，再让 App Service/Container Apps 去运行它，这一步在 Azure 的服务器上，**会产生费用**（但 Azure 新用户通常有一定免费额度）

---

## 三、当前进度（已完成）

- [x] **安装 Docker Desktop**（Mac Apple Silicon 版），已验证 `docker --version` 能正常输出(`29.8.2`)
  - 命令行工具路径 `~/.docker/bin/docker` 已加入 `~/.zshrc` 的 `PATH`，新开终端后可直接用 `docker` 命令
- [x] **项目已经改造成网页应用**：新增 [app.py](../app.py)，用 Streamlit 做了一个聊天式网页界面（上传 PDF → 提问 → 显示回答和参考原文）
- [x] **已写好 Dockerfile**：[Dockerfile](../Dockerfile)
  - 基于 `python:3.11-slim`
  - 用专门的 [requirements-deploy.txt](../requirements-deploy.txt)（不含本地用的 `sentence-transformers`/PyTorch，太重，云端改用 Gemini 的 embedding API）
  - 设置了 `EMBEDDING_PROVIDER=google` 环境变量，对应 `rag_pipeline.py` 里 `get_embeddings()` 的云端分支
  - 启动命令是 `streamlit run app.py`，监听 `8501` 端口
- [x] **已写好 .dockerignore**：排除 `venv/`、`.env`、`chroma_db/`、`documents/` 等不该打进镜像的内容

---

## 四、接下来要做的步骤（按先后顺序，不是按优先级——部署是线性流程，必须依次完成）

- [ ] **1. 本地构建镜像，验证 Dockerfile 没写错**（难度：低）
  ```bash
  cd /Users/ki/rag-starter
  docker build -t rag-starter .
  ```
  这一步会按 Dockerfile 的说明，把项目打包成一个叫 `rag-starter` 的镜像。如果这一步报错，说明 Dockerfile 或 `requirements-deploy.txt` 有问题，需要先修好再往下走。

- [ ] **2. 本地运行容器，验证网页能正常打开**（难度：低）
  ```bash
  docker run -p 8501:8501 --env-file .env -e EMBEDDING_PROVIDER=google rag-starter
  ```
  浏览器打开 `http://localhost:8501`，应该能看到 Streamlit 网页界面，上传 PDF 测试问答流程。
  **注意**：`--env-file .env` 是把本地的 `GOOGLE_API_KEY` 传进容器里，容器本身不含密钥（这也是为什么 `.dockerignore` 要排除 `.env`——镜像不应该内置密钥）。

- [x] **3. 确认 `GOOGLE_API_KEY` 支持 embedding 接口**（已完成）
  本地用 `docker run ... -e EMBEDDING_PROVIDER=google` 跑起来后，上传职務経歴書 PDF、问"他叫什么"，成功检索并正确回答"他叫張琪（张琪）"——证明 `GoogleGenerativeAIEmbeddings` 和生成模型都能正常调用，key 权限没问题。
  排查笔记：期间一度卡在"正在生成"很久没反应，排查过 DNS 解析（正常）、TCP 443 连接（正常），最后确认只是**首次调用较慢**（冷启动+库内部重试机制），不是网络或权限故障，多等一会儿就出结果了。

- [ ] **4. 注册/登录 Azure 账号，安装 Azure CLI**（难度：低）
  - 去 https://azure.microsoft.com/ 注册账号（新用户通常有免费额度）
  - 本地安装 Azure 命令行工具：
    ```bash
    brew install azure-cli
    az login
    ```
    `az login` 会打开浏览器，登录你的 Azure 账号完成授权。

- [x] **5. 创建 Azure 资源组（Resource Group）**（已完成）
  资源组是 Azure 里"把一堆相关资源打包管理"的容器，方便以后一起删除/管理。已创建 `rag-starter-rg`（`japaneast`），`provisioningState: Succeeded`。

- [ ] **6. 推送镜像到仓库 —— 改用 Docker Hub（原计划的 Azure ACR 没有免费层，已排除）**（难度：中）

  **为什么换成 Docker Hub**：Azure 自己的镜像仓库 ACR，哪怕最便宜的 Basic 档也要约 $0.17/天（折合每月 5 美元左右）、按天计费、没有免费层，这笔钱躲不掉。而 Docker Hub（Docker 官方的镜像仓库）**个人账号永久免费**（公开仓库无限制，私有仓库也有免费额度），并且 Azure Container Apps 不要求镜像必须放在 ACR——它可以直接从 Docker Hub 拉镜像，两者完全兼容。换成 Docker Hub 后，这一步彻底不花钱。

  ```bash
  # 去 https://hub.docker.com 注册账号（如果还没有）
  docker login
  docker tag rag-starter <你的DockerHub用户名>/rag-starter:latest
  docker push <你的DockerHub用户名>/rag-starter:latest
  ```
  默认推送的是**公开仓库**（任何人能看到镜像内容，但不含密钥——`GOOGLE_API_KEY` 是运行时注入的，不在镜像里，所以公开也不算泄密，只是代码逻辑会暴露）。如果介意，去 Docker Hub 网页把这个仓库设成 Private（免费额度内可以设 1 个私有仓库）。

- [x] **7. 创建 Azure 服务来运行这个镜像 —— 改用 Container Apps（原计划的 App Service 免费层不支持自定义容器，已排除）**（难度：中）

  **7a. 装 Container Apps 扩展、注册所需的资源提供者**（只需做一次）
  ```bash
  az extension add --name containerapp --upgrade
  az provider register --namespace Microsoft.App
  az provider register --namespace Microsoft.OperationalInsights
  ```

  **7b. 创建 Container Apps 环境**（相当于"运行环境"的壳，Container App 实例要挂在这个环境下）
  ```bash
  az containerapp env create \
    --name rag-starter-env \
    --resource-group rag-starter-rg \
    --location japaneast
  ```

  **7c. 如果仓库是 Private，才需要告诉 Container Apps 怎么登录 Docker Hub**（仓库是 Public 的话，这一步完全跳过，直接看 7d）
  如果把 Docker Hub 仓库设成了 Private，就需要在 7d 创建命令里额外加上：
  `--registry-server docker.io --registry-username <你的DockerHub用户名> --registry-password <你的DockerHub密码或access token>`
  （建议用 Docker Hub 的 access token 代替真实密码，在 Docker Hub 网页 Account Settings → Security 里生成。）

  **7d. 创建 Container App，把镜像跑起来**（环境变量/密钥也在这一步一起配置）
  ```bash
  az containerapp create \
    --name rag-starter-app \
    --resource-group rag-starter-rg \
    --environment rag-starter-env \
    --image <你的DockerHub用户名>/rag-starter:latest \
    --target-port 8501 \
    --ingress external \
    --secrets google-api-key=<你的真实GOOGLE_API_KEY> \
    --env-vars GOOGLE_API_KEY=secretref:google-api-key EMBEDDING_PROVIDER=google \
    --min-replicas 0 --max-replicas 1
  ```
  （以上命令假设仓库是 Public，所以没有 `--registry-*` 参数；如果是 Private，按 7c 的说明补上对应参数。）

  关键参数解释：
  - `--image <你的DockerHub用户名>/rag-starter:latest`：Container Apps 默认就会去 Docker Hub（`docker.io`）找这个镜像，不需要额外指定仓库地址
  - `--target-port 8501`：对应 Dockerfile 里 Streamlit 监听的端口
  - `--ingress external`：允许外部（互联网）访问，不加这个只能在 Azure 内网访问
  - `--secrets` + `--env-vars ...=secretref:...`：Container Apps 自己的密钥管理方式，`GOOGLE_API_KEY` 不会明文存在配置里
  - `--min-replicas 0`：**省钱的关键**，没人访问时自动缩到 0 个实例，不跑就不计费；来了请求再自动启动（会有几秒冷启动延迟，个人项目可以接受）

  这一步已经把原来第8步"配置环境变量"的内容合并进来了，不用再单独跑一次 `az webapp config appsettings set`（那是 App Service 专用命令，Container Apps 不适用）。

- [ ] **8. 查看分配的网址，验证部署成功**（难度：低）
  ```bash
  az containerapp show \
    --name rag-starter-app \
    --resource-group rag-starter-rg \
    --query properties.configuration.ingress.fqdn -o tsv
  ```
  会输出类似 `rag-starter-app.xxxxx.japaneast.azurecontainerapps.io` 的域名，浏览器打开（记得加 `https://` 前缀）验证能否正常使用。

- [ ] **9.（可选）配置自定义域名 / HTTPS 证书**（难度：中，优先级低，想要正式一点再做）

---

## 五、费用提醒

- 本地 `docker build` / `docker run`：免费
- **Docker Hub（镜像仓库）**：个人账号永久免费，不花钱——已用它替代 Azure 自己的 ACR（ACR 没有免费层，Basic 也要约 $5/月）
- **Azure Container Apps（运行容器）**：按量计费，但每月有长期有效的免费额度（18万 vCPU-秒 + 36万 GiB-秒内存 + 200万次请求），配合 `--min-replicas 0`（无人访问时自动缩到 0），个人测试项目基本能落在免费额度内，不花钱或花很少
- ~~ACR~~：已排除，见上方第6步的说明，改用 Docker Hub
- ~~App Service~~：已排除，免费层（F1）不支持自定义 Docker 容器，要用容器必须升级到 Basic 及以上（约 $13/月起），不如 Container Apps 划算
- 目前这套方案（Docker Hub + Container Apps）理论上**可以做到完全不花钱**。但 Container Apps 环境本身（`az containerapp env create` 创建的那个"壳"）在极少数场景下可能产生少量基础设施费用，保险起见，**部署测试完如果暂时不用了，还是建议执行 `az group delete --name rag-starter-rg` 把整个资源组删掉**。

---

*这份笔记由 Claude 根据 2026-10-07 的项目状态生成，Azure 的具体命令/服务名以官方文档为准，实际操作时建议对照当前 Azure 门户界面核对。*

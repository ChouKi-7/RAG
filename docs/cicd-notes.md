# rag-starter CI/CD 构建笔记

> 写给：刚开始接触 CI/CD、还不熟悉 GitHub Actions 的自己。
> 用途：忘了 CI/CD 搭到哪一步、或者为什么要做某一步时，回来看这篇。

---

## 一、这次要做什么（目标）

现在每次改代码想更新线上版本，都要手动跑这三步（见 [docs/commands-cheatsheet.md](commands-cheatsheet.md) 第五节）：

```bash
docker buildx build --platform linux/amd64 -t <DockerHub用户名>/rag-starter:latest --push .
az containerapp update --name rag-starter-app --resource-group rag-starter-rg --image <DockerHub用户名>/rag-starter:latest
```

目标是把这三步**自动化**：以后只需要改代码、`git push`，GitHub 会自动帮你构建镜像、推送到 Docker Hub、通知 Azure 拉取新版本——这整套自动化流程就叫 **CI/CD**（持续集成 / 持续部署）。

---

## 二、关键概念（新手向解释）

| 术语 | 是什么 |
|---|---|
| **CI（持续集成）** | 每次代码提交后自动跑检查（测试、lint），尽早发现问题 |
| **CD（持续部署）** | 检查通过后自动把新版本发布到生产环境，不用人工手动操作 |
| **GitHub Actions** | GitHub 自带的自动化工具，能在你 push 代码后，在 GitHub 的服务器上自动跑一套你写好的脚本（叫 "workflow"） |
| **Secrets** | GitHub 仓库里专门存密钥/凭证的地方，workflow 运行时可以读取，但不会显示在代码里，也不会被其他人看到 |
| **服务主体（Service Principal）** | Azure 里专门给"自动化程序"用的一个"机器人账号"，权限可以限定在某个资源组，不用把你自己的账号凭证交出去 |

**为什么需要 Secrets/服务主体，而不是直接把密码写进 workflow 文件**：workflow 文件是提交进 git 仓库的，任何能看到仓库的人都能看到这个文件的内容——如果把真实密码写在里面，等于公开密码。Secrets 是 GitHub 专门设计的"安全存放密钥"的地方，workflow 引用的时候只会看到 `***`，不会泄露。

---

## 三、当前进度（已完成）

- [x] 第1～5步全部完成，`.github/workflows/deploy.yml` 已经跑通一次完整的自动部署（构建镜像→推送 Docker Hub→更新 Azure Container App），全部变成绿色 ✓

---

## 四、接下来要做的步骤（按先后顺序，不是按优先级——每一步都依赖前一步）

- [x] **1. 生成 Docker Hub Access Token**（已完成）
  - 去 https://hub.docker.com/settings/security
  - 点 "New Access Token"，起个名字（比如 `github-actions`），权限选 **Read & Write**
  - 生成后**立刻复制保存**（只显示一次），先存进本地密码管理器
  - **不要**把这个 token 直接粘贴进聊天记录或代码里
  **踩坑记录（重要）**：第一次生成的 token 不小心截图发进了聊天记录里，当场**吊销作废**重新生成了一个，没有继续使用泄露过的那个——提醒自己：密钥一旦进了聊天记录/截图，就必须当作已泄露处理，直接作废重开，不要心存侥幸。

- [x] **2. 创建 Azure 服务主体（给自动化专用的身份）**（已完成）
  ```bash
  az ad sp create-for-rbac \
    --name "github-actions-rag-starter" \
    --role contributor \
    --scopes /subscriptions/<你的订阅ID>/resourceGroups/rag-starter-rg \
    --sdk-auth
  ```
  `<你的订阅ID>` 可以用 `az account show --query id -o tsv` 查到。
  执行后会输出一段 JSON（含 `clientId`、`clientSecret`、`subscriptionId`、`tenantId`），**只显示这一次**，完整复制保存下来。
  **注意**：`--scopes` 把权限限定在 `rag-starter-rg` 这一个资源组，不是整个 Azure 账号的权限，就算这个凭证泄露，影响范围也是可控的。

- [x] **3. 把凭证存进 GitHub 仓库的 Secrets**（已完成）
  仓库页面 → Settings → Secrets and variables → Actions → New repository secret，依次添加：

  | Secret 名字 | 值 |
  |---|---|
  | `DOCKERHUB_USERNAME` | 你的 Docker Hub 用户名 |
  | `DOCKERHUB_TOKEN` | 第1步生成的 token |
  | `AZURE_CREDENTIALS` | 第2步那一整段 JSON |

  **踩坑记录**：GitHub 仓库自己的 Settings、GitHub 个人账号的 Settings、Docker Hub 自己的 Settings，这三个长得有点像，容易找错地方——Secrets 功能**只存在于"某个具体仓库"自己的 Settings 里**（仓库页面顶部标签栏最右边的 Settings，不是左上角头像那个账号设置）。
  另外 Secret 一旦保存就**无法再查看原值**，编辑页面永远是空白输入框，只能整个覆盖重写，这是刻意设计的安全机制，不是 bug。

- [x] **4. 创建 workflow 文件**（已完成，内容跟下面一致）
  在项目根目录创建 `.github/workflows/deploy.yml`：
  ```yaml
  name: Build and Deploy

  on:
    push:
      branches: [main]

  jobs:
    build-and-deploy:
      runs-on: ubuntu-latest
      steps:
        - name: Checkout code
          uses: actions/checkout@v4

        - name: Set up Docker Buildx
          uses: docker/setup-buildx-action@v3

        - name: Login to Docker Hub
          uses: docker/login-action@v3
          with:
            username: ${{ secrets.DOCKERHUB_USERNAME }}
            password: ${{ secrets.DOCKERHUB_TOKEN }}

        - name: Build and push image
          uses: docker/build-push-action@v6
          with:
            context: .
            platforms: linux/amd64
            push: true
            tags: ${{ secrets.DOCKERHUB_USERNAME }}/rag-starter:latest

        - name: Azure Login
          uses: azure/login@v2
          with:
            creds: ${{ secrets.AZURE_CREDENTIALS }}

        - name: Update Container App
          uses: azure/CLI@v2
          with:
            inlineScript: |
              az containerapp update \
                --name rag-starter-app \
                --resource-group rag-starter-rg \
                --image ${{ secrets.DOCKERHUB_USERNAME }}/rag-starter:latest
  ```
  这份 workflow 做的事，跟之前手动敲的那几条命令完全对应：构建镜像（用 buildx，保证 amd64 架构）→ 推送到 Docker Hub → 登录 Azure → 更新 Container App。

- [x] **5. 提交并推送，验证自动化生效**（已完成）
  ```bash
  git add .github/workflows/deploy.yml
  git commit -m "add CI/CD workflow"
  git push
  ```
  （实际操作时用的是 VS Code 的"源代码管理"面板点击完成的，效果跟命令行完全一样。）
  推送后去仓库页面的 **Actions** 标签页（或 VS Code 的 GitHub Actions 插件），能看到 workflow 实时运行状态（黄色圆圈 = 进行中，绿色勾 = 成功，红叉 = 失败）。

  **踩坑记录（重要）**：第一次跑，`Build and push image` 这一步报错：
  ```
  Error: buildx failed with: ERROR: failed to build: failed to solve: failed to fetch oauth token:
  unexpected status from GET request to https://auth.docker.io/token?...: 401 Unauthorized:
  access token has insufficient scopes
  ```
  token 创建时权限（Read & Write）本身是对的，真正原因是 **`DOCKERHUB_TOKEN` 这个 Secret 存的内容跟实际 token 对不上**（复制粘贴的时候出了点问题，具体没查清是多了空格还是复制不完整——因为 Secret 没法回看内容，只能排除法处理）。
  → 解决办法：重新生成一个新 token，这次用 Docker Hub 页面自带的 "Copy" 按钮而不是手动框选，再去 GitHub 把 `DOCKERHUB_TOKEN` 这个 Secret **整个覆盖**成新值。
  → 改完不用重新 push 代码，去 Actions 运行记录页面点 **"Re-run jobs" → "Re-run failed jobs"** 就能直接重跑失败的部分，第二次跑全部变绿，确认问题解决。
  教训：**Docker Hub token 复制时一定要用页面自带的 Copy 按钮**，手动选中容易漏字符/多空格，这类错误报出来的提示（"insufficient scopes"）会让人误以为是权限选错了，其实是复制粘贴的问题，排查时不要被报错字面意思带偏。

- [ ] **6.（验证）改一行代码，测试全自动流程**（难度：低）
  随便改一点代码（比如改个文案），`git push`，不用手动跑任何 docker/az 命令，几分钟后直接去应用网址刷新看效果，确认真的自动生效了。

---

## 五、费用提醒

- **Docker Hub Access Token / Azure 服务主体**：免费，只是身份权限配置，不是计算资源
- **GitHub Actions 运行时间**：仓库是 Public（公开）→ 完全免费、不限时长；Private（私有）→ 免费账号每月 2000 分钟额度，这个项目偶尔跑几次完全够用
- 这套自动化**不会比你手动操作多花钱**，只是把手动敲的命令自动化了而已

---

## 六、安全提醒（重要）

- Docker Hub token、Azure 服务主体的 JSON，**永远不要**粘贴到聊天记录、代码、或者任何会被提交进 git 的文件里，只能填进 GitHub 的 Secrets 设置页面
- 如果不小心泄露了，去 Docker Hub / Azure 把对应的 token / 服务主体**立刻删除或重新生成**，不要心存侥幸
- `az ad sp create-for-rbac` 的 `--scopes` 一定要限定到具体资源组（`rag-starter-rg`），不要用更大范围的权限

---

*这份笔记由 Claude 根据 2026-10-21 的讨论整理，GitHub Actions 的具体语法以官方文档为准（Docker/Azure 官方 Action 版本号可能会更新，使用前建议核对一下最新版本号）。*

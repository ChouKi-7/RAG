# rag-starter CI/CD構築ノート

> 対象：CI/CDに触れ始めたばかりで、GitHub Actionsにまだ不慣れな自分へ。
> 使い方：CI/CDがどこまで進んだか、なぜその手順をやるのか忘れたら、これを読めば思い出せる。

---

## 一、今回やること（目標）

現在コードを変更して本番環境を更新するたびに、この3ステップを手動で実行している（[docs/commands-cheatsheet.md](commands-cheatsheet.md) の第五節参照）：

```bash
docker buildx build --platform linux/amd64 -t <DockerHubユーザー名>/rag-starter:latest --push .
az containerapp update --name rag-starter-app --resource-group rag-starter-rg --image <DockerHubユーザー名>/rag-starter:latest
```

目標はこの3ステップを**自動化**すること：今後はコードを変更して `git push` するだけで、GitHubが自動的にイメージをビルドし、Docker Hubにプッシュし、Azureに新バージョンの取得を通知してくれる——この一連の自動化の仕組みを **CI/CD**（継続的インテグレーション／継続的デプロイ）と呼ぶ。

---

## 二、重要な概念（初心者向け解説）

| 用語 | 何か |
|---|---|
| **CI（継続的インテグレーション）** | コードがコミットされるたびに自動でチェック（テスト、lint）を実行し、問題を早期に発見する |
| **CD（継続的デプロイ）** | チェックが通過したら自動的に新バージョンを本番環境に公開し、手動操作をなくす |
| **GitHub Actions** | GitHub標準の自動化ツール。コードをpushした後、GitHubのサーバー上であらかじめ書いておいたスクリプト（「workflow」と呼ぶ）を自動実行できる |
| **Secrets** | GitHubリポジトリ内の、鍵・認証情報を専用に保管する場所。workflow実行時に読み取れるが、コードには表示されず、他人にも見えない |
| **サービスプリンシパル（Service Principal）** | Azureにおける「自動化プログラム専用」のアカウント。特定のリソースグループに権限を限定でき、自分自身のアカウント認証情報を渡す必要がない |

**なぜ Secrets／サービスプリンシパルが必要で、workflowファイルに直接パスワードを書いてはいけないのか**：workflowファイルはgitリポジトリにコミットされるため、リポジトリを見られる人は誰でもこのファイルの内容を見られる——実際のパスワードをそこに書くのは、パスワードを公開するのと同じこと。Secretsは「鍵を安全に保管する」ためにGitHubが用意した仕組みで、workflowから参照しても `***` としか表示されず、漏洩しない。

---

## 三、現在の進捗（完了済み）

- [ ] まだなし、未着手

---

## 四、これからやる手順（先後順——優先度順ではない。各手順が前の手順に依存している）

- [ ] **1. Docker Hub Access Token を生成する**（難易度：低）
  - https://hub.docker.com/settings/security を開く
  - "New Access Token" をクリックし、名前を付ける（例：`github-actions`）、権限は **Read & Write** を選択
  - 生成後**すぐにコピーして保存**（一度しか表示されない）。まずローカルのパスワードマネージャーに保存する
  - このtokenをチャットやコードに**直接貼り付けない**こと

- [ ] **2. Azureサービスプリンシパルを作成する（自動化専用のID）**（難易度：中）
  ```bash
  az ad sp create-for-rbac \
    --name "github-actions-rag-starter" \
    --role contributor \
    --scopes /subscriptions/<サブスクリプションID>/resourceGroups/rag-starter-rg \
    --sdk-auth
  ```
  `<サブスクリプションID>` は `az account show --query id -o tsv` で確認できる。
  実行すると `clientId`、`clientSecret`、`subscriptionId`、`tenantId` を含むJSONが出力される（**一度しか表示されない**）。完全にコピーして保存すること。
  **注意**：`--scopes` で権限を `rag-starter-rg` という1つのリソースグループに限定している。Azureアカウント全体の権限ではないため、万一この認証情報が漏洩しても影響範囲は限定的。

- [ ] **3. 認証情報をGitHubリポジトリのSecretsに保存する**（難易度：低）
  リポジトリページ → Settings → Secrets and variables → Actions → New repository secret で、以下を順に追加：

  | Secret名 | 値 |
  |---|---|
  | `DOCKERHUB_USERNAME` | Docker Hubのユーザー名 |
  | `DOCKERHUB_TOKEN` | 手順1で生成したtoken |
  | `AZURE_CREDENTIALS` | 手順2で出力されたJSON全体 |

- [ ] **4. workflowファイルを作成する**（難易度：中、この手順は鍵を扱わないのでリポジトリに直接書いてよい）
  プロジェクトのルートに `.github/workflows/deploy.yml` を作成：
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
  このworkflowがやっていることは、これまで手動で実行していたコマンドと完全に対応している：イメージをビルド（buildxでamd64アーキテクチャを保証）→ Docker Hubへプッシュ → Azureにログイン → Container Appを更新。

- [ ] **5. コミット・プッシュして自動化が動くことを確認する**（難易度：低）
  ```bash
  git add .github/workflows/deploy.yml
  git commit -m "add CI/CD workflow"
  git push
  ```
  プッシュ後、リポジトリページの **Actions** タブを開くと、新しいworkflowが実行されているのが見える（黄色い丸＝実行中、緑のチェック＝成功、赤いバツ＝失敗）。クリックすると各ステップの詳細ログが見られ、問題の切り分けに便利。

- [ ] **6.（検証）コードを1行変更し、全自動フローをテストする**（難易度：低）
  適当にコードを少し変更して（例えば文言を変える程度）、`git push` する。docker/azコマンドを一切手動で実行せず、数分後にアプリのURLを更新して変更が反映されているか確認し、本当に自動化が動いていることを確かめる。

---

## 五、費用についての注意

- **Docker Hub Access Token／Azureサービスプリンシパル**：無料。これらは身分・権限の設定であり、計算リソースではない
- **GitHub Actionsの実行時間**：リポジトリがPublic（公開）→ 完全無料・無制限。Private（非公開）→ 無料アカウントは毎月2000分の無料枠があり、このプロジェクトの頻度なら十分足りる
- この自動化は**手動操作より費用がかかるわけではない**。手動で打っていたコマンドを自動化しただけ

---

## 六、セキュリティ上の注意（重要）

- Docker Hub token、AzureサービスプリンシパルのJSONは、**絶対に**チャット、コード、あるいはgitにコミットされるいかなるファイルにも貼り付けないこと。GitHubのSecrets設定画面にのみ入力する
- 万一漏洩した場合は、Docker Hub／Azure側で該当のtoken・サービスプリンシパルを**即座に削除または再生成**し、放置しないこと
- `az ad sp create-for-rbac` の `--scopes` は必ず具体的なリソースグループ（`rag-starter-rg`）に限定し、それより広い権限は与えないこと

---

*このノートは2026-10-21の議論をもとにClaudeが作成したもの。GitHub Actionsの具体的な構文は公式ドキュメントが正であり、Docker/Azure公式Actionのバージョン番号は更新される可能性があるため、使用前に最新バージョンを確認することを推奨する。*

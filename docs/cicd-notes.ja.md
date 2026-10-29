# rag-starter CI/CD構築ノート

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

- [x] 手順1〜5がすべて完了。`.github/workflows/deploy.yml` が一連の自動デプロイ（イメージビルド→Docker Hubへプッシュ→Azure Container Appの更新）を正常に完走し、すべて緑のチェック ✓ になった

---

## 四、これからやる手順（先後順——優先度順ではない。各手順が前の手順に依存している）

- [x] **1. Docker Hub Access Token を生成する**（完了）
  - https://hub.docker.com/settings/security を開く
  - "New Access Token" をクリックし、名前を付ける（例：`github-actions`）、権限は **Read & Write** を選択
  - 生成後**すぐにコピーして保存**（一度しか表示されない）。まずローカルのパスワードマネージャーに保存する
  - このtokenをチャットやコードに**直接貼り付けない**こと
  **トラブルシューティングメモ（重要）**：最初に生成したtokenを誤ってスクリーンショットでチャットに貼ってしまい、その場で**失効させて**新しく生成し直した。漏洩したtokenはそのまま使い続けなかった——教訓：鍵がチャット履歴やスクリーンショットに一度でも入ったら、「漏洩した」ものとして扱い、様子見せずすぐに失効・再生成すること。

- [x] **2. Azureサービスプリンシパルを作成する（自動化専用のID）**（完了）
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

- [x] **3. 認証情報をGitHubリポジトリのSecretsに保存する**（完了）
  リポジトリページ → Settings → Secrets and variables → Actions → New repository secret で、以下を順に追加：

  | Secret名 | 値 |
  |---|---|
  | `DOCKERHUB_USERNAME` | Docker Hubのユーザー名 |
  | `DOCKERHUB_TOKEN` | 手順1で生成したtoken |
  | `AZURE_CREDENTIALS` | 手順2で出力されたJSON全体 |

  **トラブルシューティングメモ**：GitHubリポジトリ自身のSettings、GitHub個人アカウントのSettings、Docker Hub自身のSettingsの3つは見た目が似ていて間違えやすい——Secrets機能は**特定のリポジトリ自身のSettings内にのみ存在する**（リポジトリページ上部タブの一番右のSettingsであり、左上のアバターから開くアカウント設定ではない）。
  また、一度保存したSecretは**元の値を二度と確認できない**。編集画面は常に空の入力欄になっており、これは意図的なセキュリティ設計であってバグではない。上書きで新しい値を丸ごと入れ直すことしかできない。

- [x] **4. workflowファイルを作成する**（完了、内容は下記の通り）
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

- [x] **5. コミット・プッシュして自動化が動くことを確認する**（完了）
  ```bash
  git add .github/workflows/deploy.yml
  git commit -m "add CI/CD workflow"
  git push
  ```
  （実際にはVS Codeの「ソース管理」パネルをクリックして操作した。コマンドラインと効果は同じ。）
  プッシュ後、リポジトリページの **Actions** タブ（またはVS CodeのGitHub Actions拡張機能）でworkflowのリアルタイム実行状況が見られる（黄色い丸＝実行中、緑のチェック＝成功、赤いバツ＝失敗）。

  **トラブルシューティングメモ（重要）**：初回実行時、`Build and push image` のステップで以下のエラーが発生：
  ```
  Error: buildx failed with: ERROR: failed to build: failed to solve: failed to fetch oauth token:
  unexpected status from GET request to https://auth.docker.io/token?...: 401 Unauthorized:
  access token has insufficient scopes
  ```
  token作成時の権限（Read & Write）自体は正しく、本当の原因は **`DOCKERHUB_TOKEN` というSecretに保存した内容が実際のtokenと一致していなかった**こと（コピー＆ペーストの際に何らかの問題が発生——余分なスペースが入ったのか不完全なコピーだったのか、Secretは内容を確認し直せないため特定はできなかった）。
  → 対処法：新しいtokenを再生成し、今度はDocker Hubページ自体の「Copy」ボタンを使い（手動で選択しない）、GitHubの `DOCKERHUB_TOKEN` Secretを**丸ごと上書き**した。
  → 修正後はコードを再pushする必要はなく、Actionsの実行履歴ページで **「Re-run jobs」→「Re-run failed jobs」** をクリックするだけで失敗した部分だけ再実行できる。2回目の実行ですべて緑になり、問題解決を確認した。
  教訓：**Docker Hub tokenをコピーする際は必ずページ自体のCopyボタンを使うこと**。手動選択は文字の欠落や余分なスペースが入りやすく、そのせいで出るエラー（「insufficient scopes」）は権限設定を誤ったかのような誤解を招くが、実際はコピー＆ペーストの問題であることが多い。エラー文の字面に惑わされず調査すること。

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

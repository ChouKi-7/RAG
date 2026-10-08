# rag-starter Azureデプロイノート

> 対象：デプロイを学び始めたばかりで、まだ Docker / Azure の概念に不慣れな自分へ。
> 使い方：デプロイがどこまで進んだか、なぜその手順をやるのか忘れたら、これを読めば思い出せる。

---

## 一、今回やること（目標）

今ローカルで動いているこの RAG プロジェクトを、**他の人もURLからアクセスできるWebアプリ**に変え、Azure（マイクロソフトのクラウドプラットフォーム）上にデプロイする。

全体の流れは2段階：
1. **ローカル**：プロジェクトを「コンテナイメージ」（Dockerイメージ）にまとめる——「コード＋実行環境＋依存ライブラリ」を、どのマシンでもそのまま動く箱に詰め込むイメージ
2. **クラウド**：その箱をAzureに送り、24時間稼働させ、URLを割り当ててもらう

---

## 二、いくつかの重要な概念（初心者向け解説）

| 用語 | 何か | たとえ |
|---|---|---|
| **Docker** | 「パッケージ化＋コンテナ実行」のツール | コンテナの梱包機 |
| **Dockerfile** | 「梱包手順書」。どの土台を使い、何を詰めて、どう起動するかを書く | 梱包リスト |
| **イメージ（image）** | Dockerfileの通りに梱包された「箱」。静的なファイル | 梱包済みでまだ開封していないコンテナ |
| **コンテナ（container）** | イメージが「実行された」後の状態 | コンテナが開封され、中の工場が実際に稼働している状態 |
| **ACR（Azure Container Registry）** | Azureが提供する「イメージ保管庫」。自分のイメージを置く場所 | コンテナ埠頭の倉庫 |
| **App Service / Container Apps** | Azureが提供する「コンテナを実行する」サービス。24時間イメージを動かし、URLを割り当ててくれる | コンテナ内の工場を実際に稼働させる建屋 |

**ローカルテスト vs クラウドデプロイの違い**：
- ローカルで `docker build` + `docker run` をするのは「箱がちゃんと動くか梱包テストする」ため。これは**無料**で、自分のPC上で完結する
- 本当の「デプロイ」は、この箱をACRに送り、App Service/Container Appsに実行させること。これはAzureのサーバー上で行われ、**費用が発生する**（ただしAzureの新規ユーザーには通常一定の無料枠がある）

---

## 三、現在の進捗（完了済み）

- [x] **Docker Desktop をインストール**（Mac Apple Silicon版）。`docker --version` が正常に出力されることを確認済み（`29.8.2`）
  - コマンドラインツールのパス `~/.docker/bin/docker` を `~/.zshrc` の `PATH` に追加済み。新しいターミナルを開けば直接 `docker` コマンドが使える
- [x] **プロジェクトをWebアプリに改造済み**：[app.py](../app.py) を新規追加。Streamlitでチャット形式のWeb画面を作成（PDFアップロード → 質問 → 回答と参照元を表示）
- [x] **Dockerfile を作成済み**：[Dockerfile](../Dockerfile)
  - `python:3.11-slim` をベースに使用
  - 専用の [requirements-deploy.txt](../requirements-deploy.txt) を使用（ローカル用の `sentence-transformers`/PyTorchは含まない。重すぎるため、クラウドではGeminiのembedding APIに切り替え）
  - `EMBEDDING_PROVIDER=google` という環境変数を設定済み。`rag_pipeline.py` の `get_embeddings()` のクラウド用分岐に対応
  - 起動コマンドは `streamlit run app.py`、`8501` ポートを監視
- [x] **.dockerignore を作成済み**：`venv/`、`.env`、`chroma_db/`、`documents/` など、イメージに含めるべきでないものを除外

---

## 四、これからやる手順（先後順——優先度順ではない。デプロイは一本道の流れなので、順番通りに進める必要がある）

- [x] **1. ローカルでイメージをビルドし、Dockerfileに誤りがないか確認**（完了）
  ```bash
  cd /Users/ki/rag-starter
  docker build -t rag-starter .
  ```
  ビルド成功。**注意**：この時デフォルトでビルドされたのは **arm64アーキテクチャ**（本機がApple Siliconのため）。後でAzureにプッシュする際、Azure Container Appsが `linux/amd64` を要求することが判明し、第6手順で `docker buildx` によるクロスアーキテクチャ再ビルドが必要になった。詳細は第6手順を参照。

- [x] **2. ローカルでコンテナを実行し、Webページが正常に開くか確認**（完了）
  ```bash
  docker run -p 8501:8501 --env-file .env -e EMBEDDING_PROVIDER=google rag-starter
  ```
  ブラウザで `http://localhost:8501` を開き、PDFをアップロードして質問応答テスト成功。
  トラブルシューティングメモ：`docker run` のログに表示される `http://0.0.0.0:8501` は、そのままブラウザで開けないアドレス。`http://localhost:8501` を使う必要がある（`0.0.0.0` は「全ネットワークインターフェースを監視する」というサーバー側の自己申告であり、アクセス可能なアドレスではない）。また、フォアグラウンドで動いているコンテナは `Ctrl+C` で止まらないことがある。代替方法：新しいターミナルで `docker ps` してコンテナIDを調べ、`docker stop <ID>` で強制停止する。その後 `docker container prune` で停止済みコンテナを削除しないと、イメージが「in use」のままで削除できない。

- [x] **3. `GOOGLE_API_KEY` がembeddingインターフェースに対応しているか確認**（完了）
  ローカルで `docker run ... -e EMBEDDING_PROVIDER=google` を実行し、職務経歴書PDFをアップロードして「他叫什么（彼の名前は？）」と質問したところ、正しく検索・回答できた（PDF上の氏名を正しく回答）——`GoogleGenerativeAIEmbeddings` と生成モデルの両方が正常に呼び出せることを確認、keyの権限問題なし。
  トラブルシューティングメモ：途中「生成中」のまま長時間反応がなくなったことがあった。DNS解決（正常）、TCP 443接続（正常）を確認した結果、**初回呼び出しが単に遅かっただけ**（コールドスタート＋ライブラリ内部のリトライ機構）で、ネットワークや権限の障害ではなく、しばらく待てば結果が出ることが分かった。

- [x] **4. Azureアカウントの登録/ログイン、Azure CLI のインストール**（完了）
  - Azureアカウント登録済み（無料プラン）
  - ローカルにAzureコマンドラインツールをインストール済み：
    ```bash
    brew install azure-cli
    az login
    ```
    `az login` 成功、ブラウザで認可ログイン完了。
  トラブルシューティングメモ：**Azureの「無料」は階層を区別する必要がある**——App Serviceの無料層（F1）は**カスタムDockerコンテナに対応していない**。コンテナを使うにはBasic以上にアップグレードする必要がある。そのため第7手順では、長期有効な無料枠があり、かつコンテナに対応している Container Apps（Consumptionプラン）に変更した。

- [x] **5. Azureリソースグループ（Resource Group）の作成**（完了）
  リソースグループは、Azureにおいて「関連するリソースをひとまとめにして管理する」入れ物。後でまとめて削除・管理しやすくなる。`rag-starter-rg`（`japaneast`）を作成済み、`provisioningState: Succeeded`。

- [x] **6. イメージをレジストリにプッシュ —— Docker Hub に変更（当初予定していた Azure ACR は無料層がないため除外）**（完了）

  **なぜ Docker Hub に変更したか**：Azure自身のイメージレジストリ ACR は、最安のBasicプランでも1日あたり約$0.17（月換算で約5米ドル）かかり、日割り課金で無料層がない——この費用は避けられない。一方 Docker Hub（Docker公式のイメージレジストリ）は**個人アカウントなら永久無料**（パブリックリポジトリは無制限、プライベートリポジトリにも無料枠あり）。また Azure Container Apps はイメージを必ずしもACRに置く必要はなく、Docker Hubから直接イメージを取得できる——両者は完全に互換性がある。Docker Hubに変更したことで、この手順は完全に無料になった。リポジトリは **Public** に設定。

  最初に実行したコマンド：
  ```bash
  docker login
  docker tag rag-starter <DockerHubユーザー名>/rag-starter:latest
  docker push <DockerHubユーザー名>/rag-starter:latest
  ```
  **トラブルシューティングメモ（重要）**：最初のプッシュ後、第7d手順でContainer App作成時に以下のエラー：
  ```
  Invalid value: "xxx/rag-starter:latest": no child with platform linux/amd64 in index ...
  ```
  原因：本機がApple Silicon（arm64）のため、`docker build` はデフォルトで本機のアーキテクチャに合わせてビルドされる。しかし Azure Container Apps（Consumptionプラン）は **linux/amd64** のみサポート。
  **解決策**：`docker buildx` でクロスアーキテクチャビルドし、直接プッシュする：
  ```bash
  docker buildx build --platform linux/amd64 -t <DockerHubユーザー名>/rag-starter:latest --push .
  ```
  再プッシュ後、第7d手順の `az containerapp create` がイメージの取得・実行に成功した。
  **今後コードを変更して再デプロイするたびに、この `buildx` コマンドを使う必要がある。通常の `docker build` を使うと、このアーキテクチャ不一致エラーが再発する**。

- [x] **7. このイメージを実行するAzureサービスを作成 —— Container Apps に変更（当初予定していた App Service の無料層はカスタムコンテナに非対応のため除外）**（完了）

  **7a. Container Apps 拡張機能のインストール、必要なリソースプロバイダーの登録**（一度だけでよい）
  ```bash
  az extension add --name containerapp --upgrade
  az provider register --namespace Microsoft.App
  az provider register --namespace Microsoft.OperationalInsights
  ```

  **7b. Container Apps 環境の作成**（「実行環境」の器のようなもの。Container Appインスタンスはこの環境の下に配置される）
  ```bash
  az containerapp env create \
    --name rag-starter-env \
    --resource-group rag-starter-rg \
    --location japaneast
  ```

  **7c. リポジトリがPrivateの場合のみ、Container AppsにDocker Hubへのログイン方法を伝える**（Publicの場合はこの手順は完全にスキップして7dへ）
  Docker HubリポジトリをPrivateに設定した場合、7dの作成コマンドに以下を追加する必要がある：
  `--registry-server docker.io --registry-username <DockerHubユーザー名> --registry-password <DockerHubパスワードまたはaccess token>`
  （実際のパスワードの代わりにDocker Hubのaccess tokenを使うことを推奨。Docker HubのWeb画面 Account Settings → Security で生成できる。）

  **7d. Container App を作成し、イメージを起動**（環境変数・シークレットもこの手順でまとめて設定）
  ```bash
  az containerapp create \
    --name rag-starter-app \
    --resource-group rag-starter-rg \
    --environment rag-starter-env \
    --image <DockerHubユーザー名>/rag-starter:latest \
    --target-port 8501 \
    --ingress external \
    --secrets google-api-key=<実際のGOOGLE_API_KEY> \
    --env-vars GOOGLE_API_KEY=secretref:google-api-key EMBEDDING_PROVIDER=google \
    --min-replicas 0 --max-replicas 1
  ```
  （上記コマンドはリポジトリがPublicであることを前提としているため `--registry-*` パラメータなし。Privateの場合は7cの説明に従って対応パラメータを追加する。）

  主要パラメータの説明：
  - `--image <DockerHubユーザー名>/rag-starter:latest`：Container Apps はデフォルトで Docker Hub（`docker.io`）からこのイメージを探すため、追加でレジストリアドレスを指定する必要はない
  - `--target-port 8501`：Dockerfile内でStreamlitが監視しているポートに対応
  - `--ingress external`：外部（インターネット）からのアクセスを許可。これを付けないとAzure内部ネットワークからしかアクセスできない
  - `--secrets` + `--env-vars ...=secretref:...`：Container Apps 独自のシークレット管理方式。`GOOGLE_API_KEY` が設定情報の中に平文で残らない
  - `--min-replicas 0`：**コスト削減の肝**。誰もアクセスしていない時は自動的に0インスタンスに縮小し、動いていなければ課金されない。リクエストが来ると自動的に起動する（数秒のコールドスタート遅延があるが、個人プロジェクトなら許容範囲）

  この手順で、当初の第8手順「環境変数の設定」の内容もまとめて行っている。`az webapp config appsettings set`（App Service専用コマンドで、Container Appsには使えない）を別途実行する必要はない。

- [x] **8. 割り当てられたURLを確認し、デプロイ成功を検証**（完了）
  ```bash
  az containerapp show \
    --name rag-starter-app \
    --resource-group rag-starter-rg \
    --query properties.configuration.ingress.fqdn -o tsv
  ```
  URL `https://rag-starter-app.happyrock-4818498e.japaneast.azurecontainerapps.io/` を取得。開いて職務経歴書PDFをアップロードし「他叫什么（彼の名前は？）」と質問したところ、**正しい回答（PDF上の実際の氏名）を正常に受信**——クラウド側の全パイプライン（embedding＋検索＋生成）が完全に動作し、デプロイが正式に成功した。

  **既知の問題（今のところ対応保留）**：初回の実テスト時、回答生成のステップが「生成中」のまま約10分間反応がなかった。Azure の Log stream（パス：Azure Portal → `rag-starter-app` リソースに入る → 左メニュー「監視」→「Log stream」）を確認すると、以下のエラーが見つかった：
  ```
  Retrying ... as it raised DeadlineExceeded: 504 Deadline expired before operation could complete.
  ```
  原因：`langchain_google_genai` が内部で使用しているのは既にメンテナンス終了した `google.generativeai` パッケージ（gRPCプロトコルを使用）。gRPCはAzureとGoogleサーバー間で時々接続が不安定・タイムアウトすることがあり、ライブラリ内蔵の自動リトライ機構は最終的に成功するものの、非常に遅くなる。
  **試した修正**：`ChatGoogleGenerativeAI` / `GoogleGenerativeAIEmbeddings` に `transport="rest"` パラメータを追加——**結果はさらに悪化**。認証方式が `GOOGLE_API_KEY` ではなくGoogle Cloudの「デフォルト認証情報」を探す方式に変わってしまい、`DefaultCredentialsError` で接続自体ができなくなった。この変更は取り消し済みで、コードは元の状態に戻してある。
  **本当の長期的な解決策**（今後時間がある時にやる、優先度低）：Google公式推奨の新パッケージ `google-genai`（新バージョンの `langchain-google-genai` とセット）にアップグレードする。ただし複数の依存パッケージのバージョンが連鎖的に上がる可能性があり、プロジェクトで固定している `langchain==0.3.7` 系統と衝突する可能性があるため、別途時間を取って検証する必要があり、今ついでにやることはお勧めしない。

- [ ] **9.（任意）カスタムドメイン / HTTPS証明書の設定**（難易度：中、優先度低、もう少し本格的にしたい時にやればよい）

---

## 五、費用についての注意

- ローカルの `docker build` / `docker run`：無料
- **Docker Hub（イメージレジストリ）**：個人アカウントは永久無料、費用なし——Azure自身のACR（無料層なし、Basicでも月約$5）の代わりに使用済み
- **Azure Container Apps（コンテナ実行）**：従量課金だが、毎月長期有効な無料枠がある（18万vCPU秒 + 36万GiB秒のメモリ + 200万リクエスト）。`--min-replicas 0`（アクセスがない時は自動的に0に縮小）と組み合わせれば、個人のテストプロジェクトは基本的に無料枠内に収まり、ほぼ無料か非常に安く済む
- ~~ACR~~：除外済み。上記第6手順の説明を参照、Docker Hubに変更
- ~~App Service~~：除外済み。無料層（F1）はカスタムDockerコンテナに非対応。コンテナを使うにはBasic以上（月約$13〜）へのアップグレードが必要で、Container Appsほどお得ではない
- 現在のこの構成（Docker Hub + Container Apps）は理論上**完全無料にできる**。ただし Container Apps 環境自体（`az containerapp env create` で作成した「器」）が、ごく稀に少額のインフラ費用を発生させる可能性があるため、念のため**デプロイテストが終わってしばらく使わないなら、`az group delete --name rag-starter-rg` を実行してリソースグループごと削除することを推奨**。

---

*このノートは2026-10-07時点のプロジェクト状態をもとにClaudeが作成したもの。Azureの具体的なコマンド・サービス名は公式ドキュメントが正であり、実際の操作時は現在のAzureポータル画面と照らし合わせて確認することを推奨する。*

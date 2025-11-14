# MCP Entra ID Python Sample

Microsoft Entra ID (旧 Azure AD) 認証を使用した Model Context Protocol (MCP) サーバーのサンプル実装です。Flask フロントエンドと FastMCP バックエンドで構成され、On-Behalf-Of (OBO) フローによるダウンストリーム API へのアクセスをサポートします。

## 📋 目次

- [概要](#概要)
- [アーキテクチャ](#アーキテクチャ)
- [主な機能](#主な機能)
- [前提条件](#前提条件)
- [セットアップ](#セットアップ)
- [使用方法](#使用方法)
- [環境変数](#環境変数)
- [OBO フロー](#obo-フロー)
- [セキュリティ](#セキュリティ)
- [トラブルシューティング](#トラブルシューティング)

## 概要

このプロジェクトは、Microsoft Entra ID を使用した安全な認証フローと、FastMCP を使用した Model Context Protocol サーバーの実装例を提供します。Azure OpenAI との統合により、AI チャットエージェント機能も備えています。

### 認証フロー

```
User → Frontend (Flask) → Backend (FastMCP) → Downstream API (Azure AI Search等)
         |                    |                        |
         └→ Graph API         └→ OBO Token Exchange   └→ Resource API
```

## アーキテクチャ

### Frontend (Flask)
- **認証**: `identity.flask` ライブラリを使用した Entra ID 認証
- **セッション管理**: Flask Session による安全なセッション管理
- **UI**: シンプルなチャットインターフェース
- **AI エージェント**: Azure OpenAI を使用したチャットエージェント
- **MCP ツール統合**: 認証付き/認証不要の MCP ツールをサポート

### Backend (FastMCP)
- **認証**: JWTVerifier による委任アクセストークンの検証
- **MCP サーバー**: FastMCP を使用した標準準拠の MCP サーバー
- **OBO フロー**: Managed Identity を使用したセキュアなトークン交換
- **ツール**: セキュアな ping、ユーザー情報取得、トークン交換 API

## 主な機能

### ✅ 認証・認可
- Microsoft Entra ID による OAuth 2.0 / OpenID Connect 認証
- JWT トークンの自動検証（署名、有効期限、issuer、audience）
- スコープベースのアクセス制御
- テナント ID の検証

### ✅ On-Behalf-Of (OBO) フロー
- ダウンストリーム API 用のトークン交換
- Managed Identity によるセキュアな認証
- クライアントシークレット対応（ローカル開発用）
- 複数のリソース URI サポート

### ✅ AI チャット機能
- Azure OpenAI との統合
- ストリーミングレスポンス対応
- MCP ツールの動的呼び出し
- 認証コンテキストの保持

### ✅ MCP ツール
- **Microsoft Learn**: 認証不要の公開 MCP サーバー
- **認証済みユーザー情報**: 認証が必要な保護された MCP サーバー
- カスタムツールの簡単な追加

## 前提条件

- Python 3.10 以上
- Microsoft Entra ID テナント
- Azure OpenAI リソース（チャット機能を使用する場合）
- Azure Managed Identity（OBO フロー使用時、Azure 環境のみ）

## セットアップ

### 1. リポジトリのクローン

```bash
git clone <repository-url>
cd mcp-entraid-auth-chat-sample
```

### 2. Entra ID アプリ登録

#### Backend API アプリの登録

1. Azure Portal で「アプリの登録」を開く
2. 新しいアプリを登録（例: `MCP-Backend-API`）
3. 「API の公開」で以下を設定:
   - アプリケーション ID URI: `api://<BACKEND_CLIENT_ID>`
   - スコープを追加: `access_as_user`
   - 「<テナント名> に管理者の同意を与えます」ボタンをクリック
4. クライアント ID をメモ（`API_APP_ID`）

#### Frontend アプリの登録

1. 新しいアプリを登録（例: `MCP-Frontend-Flask`）
2. 「認証」で以下を設定:
   - リダイレクト URI: `http://localhost:5001/signin-oidc`
3. 「証明書とシークレット」でクライアントシークレットを作成
4. 「API のアクセス許可」で以下を追加:
   - Microsoft Graph: `User.Read`（委任）
   - Backend API: `access_as_user`（委任）
   - 「<テナント名> に管理者の同意を与えます」ボタンをクリック
5. クライアント ID とシークレットをメモ

### 3. 依存関係のインストール

#### Frontend

```bash
cd frontend
pip install -r requirements.txt
```

#### Backend

```bash
cd backend
pip install -r requirements.txt
```

### 4. 環境変数の設定

#### Frontend (.env)

`.env.example` をコピーして `.env` を作成し、以下の値を設定します:

```bash
cd frontend
cp .env.example .env
```

```env
# Entra ID 設定
TENANT_ID="your-tenant-id-here"
FLASK_CLIENT_ID="your-flask-client-id-here"
FLASK_CLIENT_SECRET="your-flask-client-secret-here"

# Backend API 設定
API_APP_ID="your-api-app-id-here"
API_APP_ID_URI="api://your-api-app-id-here"
BACKEND_API_BASE=http://localhost:8000

# Flask 設定
FLASK_SECRET_KEY=your-secret-key-here
REDIRECT_URI="http://localhost:5001/signin-oidc"

# Azure OpenAI 設定
AZURE_OPENAI_API_KEY='your-azure-openai-api-key-here'
AZURE_OPENAI_ENDPOINT='https://your-resource-name.openai.azure.com/'
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME='your-deployment-name'
```

#### Backend (.env)

Backend ディレクトリに `.env` ファイルを作成:

```env
# Entra ID 設定
TENANT_ID="your-tenant-id-here"
API_APP_ID="your-api-app-id-here"

# OBO フロー設定（オプション）
USE_OBO_FLOW=false
AZURE_TENANT_ID="your-tenant-id-here"
ENTRA_APP_CLIENT_ID="your-api-app-id-here"
ENTRA_APP_CLIENT_SECRET="your-client-secret-here"  # ローカル開発のみ
UMI_CLIENT_ID="your-managed-identity-client-id"  # Azure 環境のみ
TARGET_AUDIENCES="https://search.azure.com"  # カンマ区切りで複数指定可能
```

## 使用方法

### 1. Backend サーバーの起動

```bash
cd backend
python main.py
```

Backend は `http://localhost:8000` で起動します。

### 2. Frontend サーバーの起動

別のターミナルで:

```bash
cd frontend
python app.py
```

Frontend は `http://localhost:5001` で起動します。

### 3. アプリケーションへのアクセス

ブラウザで `http://localhost:5001` にアクセスします。Entra ID のログイン画面にリダイレクトされるので、認証情報を入力してログインします。

### 4. チャット機能の使用

ログイン後、チャット画面が表示されます:

- メッセージを入力して送信すると、Azure OpenAI が応答します
- 必要に応じて MCP ツールが自動的に呼び出されます
- ストリーミングでリアルタイムに応答が表示されます

### 5. OBO トークンの取得（デモ）

「Azure AI Search トークンを取得」ボタンをクリックすると、OBO フローで取得したトークン情報が表示されます。


## OBO フロー

### On-Behalf-Of (OBO) フローとは

OBO フローは、ユーザーの委任されたアクセス許可を使用して、ダウンストリーム API にアクセスするための OAuth 2.0 フローです。

### フロー図

```
1. ユーザー認証
   User → Frontend: ログイン
   Frontend → Entra ID: 認証リクエスト
   Entra ID → Frontend: アクセストークン (Graph API用)

2. 委任アクセストークンの取得
   Frontend → Entra ID: トークンリクエスト (Backend API用スコープ)
   Entra ID → Frontend: 委任アクセストークン (aud: api://{BACKEND_API})

3. OBO トークン交換
   Frontend → Backend: 委任アクセストークン
   Backend → Entra ID: OBO リクエスト + Managed Identity
   Entra ID → Backend: OBO トークン (aud: https://resource.azure.com)

4. リソースアクセス
   Backend → Azure Resource: OBO トークン
   Azure Resource → Backend: データ
   Backend → Frontend: レスポンス
```

### OBO フローの有効化

1. `.env` ファイルで `USE_OBO_FLOW=true` に設定
2. 必要な環境変数を設定（上記参照）
3. Azure 環境の場合、Managed Identity を設定
4. Entra ID アプリで Federated Credentials を設定

### サポートされるリソース

デフォルトで以下のリソースに対応:

- Azure AI Search: `https://search.azure.com`


`TARGET_AUDIENCES` 環境変数で追加のリソースを指定できます。

## セキュリティ

### 実装されているセキュリティ機能

- ✅ JWT トークンの署名検証（JWKS による公開鍵検証）
- ✅ トークンの有効期限チェック（exp, nbf クレーム）
- ✅ Issuer 検証（信頼できるテナントからの発行）
- ✅ Audience 検証（正しい API 向けのトークン）
- ✅ Tenant ID 検証（正しいテナントからのアクセス）
- ✅ スコープベースのアクセス制御
- ✅ セッションの暗号化とセキュアクッキー
- ✅ HTTPS 推奨（本番環境）

### セキュリティベストプラクティス

1. **本番環境では必ず HTTPS を使用**
2. **クライアントシークレットは環境変数で管理**
3. **Managed Identity を使用**（Azure 環境）
4. **トークンの有効期限を適切に設定**
5. **最小権限の原則に従う**
6. **定期的なセキュリティ監査**

### 参考リソース

- [Microsoft Entra ID ベストプラクティス](https://learn.microsoft.com/ja-jp/security/zero-trust/develop/protect-api)
- [OAuth 2.0 OBO フロー](https://learn.microsoft.com/ja-jp/entra/identity-platform/v2-oauth2-on-behalf-of-flow)

## トラブルシューティング

### よくある問題

#### 1. `AADSTS65001: The user or administrator has not consented`

**原因**: API のアクセス許可に同意していない

**解決方法**:
1. Azure Portal で Frontend アプリの「API のアクセス許可」を開く
2. 「管理者の同意を与えます」をクリック

#### 2. `Audience validation failed`

**原因**: トークンの audience が正しくない

**解決方法**:
- `.env` ファイルの `API_APP_ID_URI` が正しいか確認
- Backend の `AUDIENCE` 設定を確認
- Entra ID アプリの「API の公開」で ID URI が正しいか確認

#### 3. `Issuer validation failed`

**原因**: トークンの issuer が期待値と一致しない

**解決方法**:
- `TENANT_ID` が正しいか確認
- V1 と V2 エンドポイントの issuer 形式の違いに注意

#### 4. OBO トークン交換が失敗する

**原因**: OBO 設定が不完全、または Federated Credentials が未設定

**解決方法**:
- 全ての OBO 関連環境変数が設定されているか確認
- Managed Identity が正しく設定されているか確認
- Entra ID アプリで Federated Credentials が設定されているか確認

#### 5. チャットが応答しない

**原因**: Azure OpenAI の設定が不正、またはデプロイメントが存在しない

**解決方法**:
- Azure OpenAI の API キーとエンドポイントを確認
- デプロイメント名が正しいか確認
- Azure OpenAI リソースが正しくデプロイされているか確認


## ライセンス
MIT License
このプロジェクトは、サンプルコードとして提供されています。

## 参考資料

- [FastMCP Documentation](https://gofastmcp.com/)
- [Microsoft identity platform](https://learn.microsoft.com/ja-jp/entra/identity-platform/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [identity-library Documentation](https://identity-library.readthedocs.io/)
- [Azure OpenAI Service](https://learn.microsoft.com/ja-jp/azure/ai-services/openai/)

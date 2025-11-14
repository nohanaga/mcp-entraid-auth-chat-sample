# -*- coding: utf-8 -*-
import os
import logging
from flask import Flask, render_template, session, request, jsonify
from identity.flask import Auth #https://identity-library.readthedocs.io/en/latest/flask.html
from agent_framework import ChatAgent, MCPStreamableHTTPTool
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.openai import OpenAIChatClient
from agent_framework.observability import setup_observability
from azure.identity import DefaultAzureCredential

from dotenv import load_dotenv
import jwt
import json

load_dotenv()

# ロギング設定（tool callのログを表示するため）
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# agent_frameworkのログレベルをDEBUGに設定（tool call詳細を表示）
logging.getLogger('agent_framework').setLevel(logging.DEBUG)

# OpenTelemetryの可観測性を有効化（tool callが自動的にトレースされます）
print("=== OpenTelemetry 可観測性を有効化 ===")
# setup_observability()
print("=== Tool callのログがコンソールに表示されます ===\n")

app = Flask(__name__)
app.config["SESSION_TYPE"] = "filesystem"
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret_change_me")

# テナントIDとクライアント情報を環境変数から取得
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("FLASK_CLIENT_ID")
CLIENT_SECRET = os.getenv("FLASK_CLIENT_SECRET")
API_APP_ID_URI = os.getenv("API_APP_ID_URI")
BACKEND_API_BASE = os.getenv("BACKEND_API_BASE", "http://localhost:8000")

# APIスコープとGraph APIスコープ
API_SCOPES = [f"{API_APP_ID_URI}/access_as_user"]
GRAPH_SCOPES = ["User.Read"]

# Initialize Auth with the recommended pattern from identity-library docs
auth = Auth(
    app,
    client_id=CLIENT_ID,
    client_credential=CLIENT_SECRET,
    authority=f"https://login.microsoftonline.com/{TENANT_ID}",
    redirect_uri=os.getenv("REDIRECT_URI", "http://localhost:5001/redirect"),
)

def get_chat_agent(access_token=None):
    """チャットエージェントを取得または作成
    
    Args:
        access_token: Backend API (FastMCP) 用の委任アクセストークン。
                     @auth.login_required(scopes=API_SCOPES)によって自動的にキャッシュ・管理される。
                     Audience: api://{API_APP_ID}
                     
                     注: このトークンはBackend API専用です。Backend がdownstream API (AI Search等)
                     を呼ぶ場合は、Backend側でOBOフローを使用してトークンを交換する必要があります。
    """
    try:
        # Azure OpenAI設定を環境変数から取得
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
        azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
        
        if not azure_endpoint or not azure_deployment:
            print("Error: AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_CHAT_DEPLOYMENT_NAME not set")
            return None
            
        print("Initializing Azure OpenAI Chat Client:")
        print(f"  Endpoint: {azure_endpoint}")
        print(f"  Deployment: {azure_deployment}")
        print(f"  Using API Key: {bool(azure_api_key)}")
        
        # Azure OpenAI Chat Clientを作成
        if azure_api_key:
            # APIキー認証
            client = AzureOpenAIChatClient(
                endpoint=azure_endpoint,
                deployment_name=azure_deployment,
                api_key=azure_api_key,
            )

            # client = OpenAIChatClient(
            #     model_id=os.environ["OPENAI_CHAT_MODEL_ID"],
            #     api_key=os.environ["OPENAI_API_KEY"],
            # )

        else:
            # DefaultAzureCredential認証
            client = AzureOpenAIChatClient(
                endpoint=azure_endpoint,
                deployment_name=azure_deployment,
                credential=DefaultAzureCredential(),
            )

        # HTTP streaming MCP (認証不要)
        mslearn_mcp = MCPStreamableHTTPTool(
            name="Microsoft Learn",
            url="https://learn.microsoft.com/api/mcp",
            description="Microsoft Learnから情報を取得するためのツールです。質問に関連するMicrosoft Learnのコンテンツを検索し、要約して提供します。",
        )
        
        # ツールリスト
        tools = [mslearn_mcp]
        
        # 認証が必要なMCPツールの追加
        if access_token:
            auth_mcp = MCPStreamableHTTPTool(
                name="Authenticated User Info",
                url="http://localhost:8000/mcp",
                description="認証されたユーザー情報を取得するためのツールです。ユーザーのプロフィールや設定に関する情報を提供します。",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            tools.append(auth_mcp)
            print(f"  Auth MCP added with token (first 20 chars): {access_token[:20]}...")

        # エージェントを作成
        agent = ChatAgent(
            name="assistant",
            chat_client=client,
            instructions="あなたは親切なAIアシスタントです。日本語で丁寧に回答してください。必要に応じて、提供されたツールを使用してください。",
            tools=tools,
            temperature=0.7,
            max_tokens=2000,
        )

        print(f"Chat agent initialized successfully: {type(agent)}")
        return agent
    except Exception as e:
        import traceback
        print(f"Chat agent initialization error: {type(e).__name__}: {e}")
        print(traceback.format_exc())
        return None

@app.route("/")
@auth.login_required(scopes=GRAPH_SCOPES)
def index(*, context):
    """ホームページ - ログインが必要"""
    user = context['user']
    access_token = context['access_token']
    
    # トークンからテナントIDを取得
    decoded = jwt.decode(access_token, options={"verify_signature": False})
    token_tenant_id = decoded.get('tid')
    
    # 期待するテナントIDと一致するか確認
    if token_tenant_id != TENANT_ID:
        return "Access denied: Invalid tenant", 403
    
    # 以下、通常の処理
    # contextの中身を確認
    token_debug = f"Context keys: {list(context.keys())}\n"
    token_debug += f"Token type: {context.get('token_type')}\n"
    token_debug += f"Expires in: {context.get('expires_in')}\n"
    token_debug += f"Scopes: {context.get('scopes')}\n\n"
    
    # userの内容を表示
    token_debug += "=== User Info ===\n"
    token_debug += json.dumps(user, indent=2, ensure_ascii=False, default=str)
    token_debug += "\n\n"
    
    # ログイン時のトークンをデバッグ表示
    if 'access_token' in context:
        try:
            login_token = context['access_token']
            token_debug += "=== Access Token (Raw) ===\n"
            token_debug += f"Token: {login_token[:50]}... (先頭50文字のみ表示)\n\n"
            token_debug += "=== Access Token (Decoded) ===\n"
            decoded_token = jwt.decode(login_token, options={"verify_signature": False})
            token_debug += "Access Token (Graph API用):\n"
            token_debug += json.dumps(decoded_token, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            token_debug += f"トークンデコードエラー: {type(e).__name__}: {str(e)}"
    else:
        token_debug += "access_token が context に含まれていません"
    
    # セッションに保存
    session['token_debug'] = token_debug
    
    return render_template('index.html', user=user, token_debug=token_debug)


@app.post("/chat")
@auth.login_required(scopes=API_SCOPES)  # API_SCOPESで委任アクセストークンを取得（自動キャッシュ）
def chat(*, context):
    """チャットエンドポイント - Azure OpenAI Chat Agent (ストリーミング対応)
    
    identity.flaskのAuthクラスが自動的に委任アクセストークン(delegated access token)をキャッシュ・管理します:
    - 初回リクエスト: Backend API用の委任アクセストークン取得（Entra IDへのAPI呼び出しあり）
    - 2回目以降: セッションキャッシュから取得（Entra IDへのAPI呼び出しなし）
    - トークン有効期限: 通常60分、期限切れ前に自動更新
    
    注: このトークンは Backend API (FastMCP) 向けです。
    Backend が downstream API (AI Search等) を呼ぶ場合は、OBOフローでトークンを交換する必要があります。
    """
    import asyncio
    from flask import Response, stream_with_context
    
    user = context['user']
    data = request.get_json()
    
    if not data or 'message' not in data:
        return jsonify({"error": "メッセージが必要です"}), 400
    
    message = data['message']
    use_streaming = data.get('stream', True)  # デフォルトでストリーミング有効
    
    # identity.flaskのAuthが自動的にキャッシュ・管理する委任アクセストークンを取得
    # このトークンはBackend API (api://{API_APP_ID}) 向けで、downstream API には使用できません
    api_token = context['access_token']
    
    # 委任アクセストークン情報を準備（UI表示用）
    delegated_token_info = None
    try:
        decoded_token = jwt.decode(api_token, options={"verify_signature": False})
        delegated_token_info = {
            "raw": f"{api_token[:50]}... (先頭50文字のみ表示)",
            "decoded": decoded_token
        }
    except Exception as e:
        print(f"Token decode error: {e}")
    
    # チャットエージェントを取得
    agent = get_chat_agent(access_token=api_token)
    
    if agent is None:
        return jsonify({
            "error": "チャットエージェントが初期化されていません。Azure OpenAI設定を確認してください。"
        }), 500
    
    if use_streaming:
        # ストリーミングレスポンス
        # セキュリティ: agentとmessageをクロージャスコープに明示的にキャプチャ
        # 他のリクエストと混ざらないようにローカル変数として固定
        # ⚠️会話履歴を実装する場合は、ユーザーID(oidクレーム)で必ず分離する必要があります
        captured_agent = agent
        captured_message = message
        captured_delegated_token_info = delegated_token_info
        
        def generate():
            """Chunked Transfer Encoding でストリーミング"""
            import asyncio
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                chunk_count = 0
                delegated_token_sent = False  # 委任アクセストークン情報を1回だけ送信するためのフラグ
                
                # 非同期ジェネレータを同期的に実行
                async def run_stream():
                    nonlocal chunk_count, delegated_token_sent
                    try:
                        async for chunk in captured_agent.run_stream(captured_message):
                            chunk_count += 1
                            
                            # 最初のチャンクで委任アクセストークン情報を送信
                            if not delegated_token_sent and captured_delegated_token_info:
                                yield json.dumps({'obo_token': captured_delegated_token_info, 'done': False}, ensure_ascii=False) + '\n'
                                delegated_token_sent = True
                            
                            # chunk.textが存在し、Noneでないことを確認
                            try:
                                text_value = chunk.text if hasattr(chunk, 'text') else None
                                if text_value:
                                    # print(f"Chunk {chunk_count}: Sending '{text_value}'")
                                    yield json.dumps({'chunk': text_value, 'done': False}, ensure_ascii=False) + '\n'
                            except Exception as chunk_error:
                                print(f"Error accessing chunk.text: {type(chunk_error).__name__}: {chunk_error}")
                        
                        print(f"Stream completed successfully. Total chunks: {chunk_count}")
                    except Exception as e:
                        # Agent Frameworkのバグで最後のチャンクでエラーが発生する場合がある
                        # 'NoneType' object has no attribute 'content' エラーは無視
                        if "'NoneType' object has no attribute 'content'" in str(e):
                            print(f"Stream completed with known framework bug (ignored). Total chunks: {chunk_count}")
                        else:
                            # 予期しないエラーの場合はログ出力してエラーを返す
                            import traceback
                            error_msg = f"{type(e).__name__}: {str(e)}"
                            print(f"Streaming error: {error_msg}")
                            print(traceback.format_exc())
                            yield json.dumps({'error': error_msg, 'done': True}, ensure_ascii=False) + '\n'
                            return
                    
                    # 正常終了
                    print("Sending done signal...")
                    yield json.dumps({'chunk': '', 'done': True}, ensure_ascii=False) + '\n'
                    print("Done signal sent. Stream generation complete.")
                
                # 非同期ジェネレータを同期的に消費
                async_gen = run_stream()
                sent_count = 0
                while True:
                    try:
                        item = loop.run_until_complete(async_gen.__anext__())
                        sent_count += 1
                        yield item
                    except StopAsyncIteration:
                        print(f"Generator exhausted. Total items sent: {sent_count}")
                        break
                        
            finally:
                loop.close()
        
        return Response(stream_with_context(generate()), mimetype='application/json')
    else:
        # 非ストリーミングレスポンス
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(agent.run(message))
            loop.close()
            
            response_data = {
                "response": str(result),
                "user": user.get("name", "Unknown")
            }
            
            # 委任アクセストークン情報を追加
            if delegated_token_info:
                response_data["obo_token"] = delegated_token_info
            
            return jsonify(response_data)
        except Exception as e:
            return jsonify({"error": f"チャット処理エラー: {str(e)}"}), 500


@app.post("/api/get-aisearch-token")
@auth.login_required(scopes=API_SCOPES)
def get_aisearch_token(*, context):
    """Azure AI Search用のOBOトークンを取得するAPIエンドポイント
    
    MCPStreamableHTTPToolを使用してバックエンドMCPサーバーのツールを直接呼び出します。
    MCPStreamableHTTPToolはasync context managerとして使用する必要があります。
    
    フロー:
    1. Frontend → Backend: 委任アクセストークン (aud: api://{BACKEND_API})
    2. Backend → Entra ID: OBOフローでトークン交換
    3. Backend → AI Search: OBOトークン (aud: https://search.azure.com)
    
    レスポンスには以下を含みます:
    - token_result: AI Search用OBOトークン情報 (Backend がOBOフローで取得)
    - delegated_token: Frontend → Backend 間で使用した委任アクセストークン情報
    """
    import asyncio
    
    try:
        # 委任アクセストークンを取得 (Backend API向け)
        api_token = context['access_token']
        
        # 委任アクセストークン情報を準備
        delegated_token_info = None
        try:
            decoded_token = jwt.decode(api_token, options={"verify_signature": False})
            delegated_token_info = {
                "raw": f"{api_token}",
                "decoded": decoded_token
            }
        except Exception as e:
            print(f"Token decode error: {e}")
        
        # 非同期でツールを実行
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            async def call_mcp_tool():
                # MCPツールをasync context managerとして作成・接続
                async with MCPStreamableHTTPTool(
                    name="Azure AI Search Token Provider",
                    url="http://localhost:8000/mcp",
                    description="Azure AI Search用のOBOトークンを取得",
                    headers={"Authorization": f"Bearer {api_token}"},
                ) as mcp_tool:
                    # ツールを呼び出し(**kwargsで引数を渡す。引数なしの場合は何も渡さない)
                    # 戻り値: list[Contents] (TextContent, DataContent等のオブジェクト)
                    result = await mcp_tool.call_tool("get_azure_ai_search_token")
                    return result
            
            result = loop.run_until_complete(call_mcp_tool())
            
            # list[Contents]をJSON化可能な形式に変換
            result_data = []
            for content in result:
                if hasattr(content, 'text'):
                    # TextContentの場合、テキストを抽出
                    result_data.append({"type": "text", "content": content.text})
                elif hasattr(content, 'uri'):
                    # DataContent/UriContentの場合
                    result_data.append({
                        "type": "data",
                        "uri": content.uri,
                        "media_type": getattr(content, 'media_type', None)
                    })
                else:
                    # その他の場合はstr()で変換
                    result_data.append({"type": "unknown", "content": str(content)})
            
            # レスポンスを構築(AI Search用OBOトークンと委任アクセストークン情報の両方を含む)
            response_data = {
                "token_result": result_data,  # Backend がOBOフローで取得したAI Search用トークン
            }
            
            # Frontend → Backend 間で使用した委任アクセストークン情報を追加
            if delegated_token_info:
                response_data["obo_token"] = delegated_token_info
            
            return jsonify(response_data)
            
        finally:
            loop.close()
        
    except Exception as e:
        import traceback
        print(f"Error calling MCP tool: {type(e).__name__}: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            "error": f"Error: {str(e)}",
            "traceback": traceback.format_exc()
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)

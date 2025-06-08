# -*- coding: utf-8 -*-
import streamlit as st
import os
from google.oauth2 import id_token
from google.auth.transport import requests
from google_auth_oauthlib.flow import Flow
from dotenv import load_dotenv
from data_manager import save_user_data, load_user_data
from payment import verify_premium_access
from utils import get_redirect_uri
from datetime import datetime, timedelta

# 環境変数読み込み
load_dotenv()

# Google OAuth設定
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

class GoogleOAuth:
    def __init__(self):
        self.client_id = GOOGLE_CLIENT_ID
        self.client_secret = GOOGLE_CLIENT_SECRET
        
    def get_authorization_url(self, redirect_uri):
        """Google OAuth認証URLを生成"""
        try:
            # OAuth2 Flow設定
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [redirect_uri]
                    }
                },
                scopes=["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"],
                redirect_uri=redirect_uri
            )
            
            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true'
            )
            
            return authorization_url, state
            
        except Exception as e:
            st.error(f"認証URL生成エラー: {str(e)}")
            return None, None
    
    def verify_token(self, token, redirect_uri):
        """Googleトークンを検証してユーザー情報を取得"""
        try:
            # OAuth2 Flow設定
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [redirect_uri]
                    }
                },
                scopes=["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"],
                redirect_uri=redirect_uri
            )
            
            # 認証コードからトークンを取得
            flow.fetch_token(code=token)
            
            # ID token を検証
            id_info = id_token.verify_oauth2_token(
                flow.credentials.id_token,
                requests.Request(),
                self.client_id
            )
            
            return {
                'email': id_info.get('email'),
                'name': id_info.get('name'),
                'picture': id_info.get('picture'),
                'sub': id_info.get('sub')  # Google user ID
            }
            
        except Exception as e:
            st.error(f"トークン検証エラー: {str(e)}")
            return None

def init_auth_session():
    """認証セッション状態を初期化"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'user_info' not in st.session_state:
        st.session_state.user_info = None
    if 'user_plan' not in st.session_state:
        st.session_state.user_plan = 'free'  # デフォルトは無料プラン

def login_required(func):
    """ログイン必須デコレータ"""
    def wrapper(*args, **kwargs):
        if not st.session_state.get('authenticated', False):
            show_login_page()
            return None
        return func(*args, **kwargs)
    return wrapper

def show_login_page():
    """ログインページ表示"""
    st.markdown("""
    <div style="text-align: center; padding: 3rem 0;">
        <h1>RigakuGPT</h1>
        <p style="font-size: 1.2rem; color: #7f8c8d;">科学の勉強に特化したチャットボットサービス</p>
        <p style="margin: 2rem 0;">Googleでログインして始めましょう</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🔑 Googleでログイン", type="primary", use_container_width=True):
            start_oauth_flow()

def start_oauth_flow():
    """OAuth認証フローを開始"""
    oauth = GoogleOAuth()
    
    # リダイレクトURIを動的に取得
    redirect_uri = get_redirect_uri()
    
    # 認証URLを生成
    auth_url, state = oauth.get_authorization_url(redirect_uri)
    
    if auth_url:
        # セッション状態にstateを保存
        st.session_state.oauth_state = state
        
        # 認証URLにリダイレクト
        st.markdown(f'<meta http-equiv="refresh" content="0; url={auth_url}">', unsafe_allow_html=True)
        st.info("Google認証ページにリダイレクトします...")

def sync_subscription_status(user_id, user_email):
    """Stripeのサブスクリプション状態とローカルデータを同期する"""
    is_premium_on_stripe = verify_premium_access(user_email)
    
    user_data = load_user_data(user_id)
    local_plan = user_data.get('plan', 'free')

    new_plan = 'premium' if is_premium_on_stripe else 'free'

    if new_plan != local_plan:
        user_data['plan'] = new_plan
        # プランが変更された場合、セッションとファイルの両方を更新
        st.session_state.user_plan = new_plan
        if new_plan == 'free':
            # 無料プランに戻った場合、使用回数をリセット
            st.session_state.ocr_usage_count = 0
            st.session_state.question_usage_count = 0
            user_data['ocr_usage_count'] = 0
            user_data['question_usage_count'] = 0
        
        save_user_data(user_id, user_data)
        st.toast(f"プランが {new_plan.capitalize()} に更新されました。")

    return new_plan

def handle_oauth_callback():
    """OAuth認証コールバックを処理"""
    query_params = st.query_params
    
    if 'code' in query_params:
        auth_code = query_params.get('code')

        # 認証コードは一度しか使えないため、URLからすぐに削除して再利用を防ぐ
        st.query_params.clear()
        
        oauth = GoogleOAuth()
        redirect_uri = get_redirect_uri()
        user_info = oauth.verify_token(auth_code, redirect_uri)
        
        if user_info:
            user_id = user_info['sub']
            user_email = user_info['email']
            
            # ユーザーデータをロード
            user_data = load_user_data(user_id)
            
            # 最終利用日時をチェックしてリセット
            now = datetime.now()
            last_usage_time_str = user_data.get('last_usage_time')
            if last_usage_time_str:
                last_usage_time = datetime.fromisoformat(last_usage_time_str)
                if (now - last_usage_time) > timedelta(days=1):
                    user_data['ocr_usage_count'] = 0
                    user_data['question_usage_count'] = 0
                    st.toast("利用回数がリセットされました。")

            # 常に最新のuser_infoで更新
            user_data['user_info'] = user_info
            
            # Stripeとプラン状態を同期
            current_plan = sync_subscription_status(user_id, user_email)
            user_data['plan'] = current_plan
            
            # データを保存
            save_user_data(user_id, user_data)

            # セッション状態を設定
            st.session_state.authenticated = True
            st.session_state.user_info = user_info
            st.session_state.user_plan = current_plan
            st.session_state.ocr_usage_count = user_data.get('ocr_usage_count', 0)
            st.session_state.question_usage_count = user_data.get('question_usage_count', 0)
            
            # 画面を再描画してログイン後の状態を表示
            st.rerun()
        # 認証失敗時のエラーは verify_token 内で表示されるため、ここでは重複して表示しない

def get_user_plan(email):
    """ユーザーのプランを取得（簡易実装）"""
    # 実際の実装では、データベースから取得
    # ここでは簡易的に判定
    premium_users = []  # 有料ユーザーのリスト
    
    return 'premium' if email in premium_users else 'free'

def logout():
    """ログアウト処理"""
    st.session_state.authenticated = False
    st.session_state.user_info = None
    st.session_state.user_plan = 'free'
    if 'usage_count' in st.session_state:
        del st.session_state.usage_count
    st.rerun()

def show_user_info():
    """ユーザー情報表示"""
    if st.session_state.get('authenticated', False):
        user_info = st.session_state.user_info
        plan = st.session_state.user_plan
        
        with st.sidebar:
            st.markdown("### 👤 ユーザー情報")
            
            if user_info.get('picture'):
                st.image(user_info['picture'], width=60)
            
            st.write(f"**名前:** {user_info['name']}")
            st.write(f"**Email:** {user_info['email']}")
            
            # プラン表示
            plan_color = "#28a745" if plan == 'premium' else "#6c757d"
            plan_text = "Premium" if plan == 'premium' else "Free"
            st.markdown(f"**プラン:** <span style='color: {plan_color}; font-weight: bold;'>{plan_text}</span>", 
                       unsafe_allow_html=True)
            
            # 使用制限表示
            show_usage_limits()
            
            # ログアウトボタン
            if st.button("🚪 ログアウト", use_container_width=True):
                logout()

def show_usage_limits():
    """使用制限表示"""
    plan = st.session_state.user_plan
    
    if plan == 'free':
        # 使用回数を取得
        ocr_count = st.session_state.get('ocr_usage_count', 0)
        question_count = st.session_state.get('question_usage_count', 0)
        
        st.markdown("### 📊 使用状況")
        st.write(f"OCR実行: {ocr_count}回")
        st.write(f"質問回数: {question_count}回")
        
        # プレミアムアップグレードボタン
        if st.button("⭐ Premiumにアップグレード", use_container_width=True):
            show_upgrade_modal()
    else:
        st.markdown("### ⭐ Premium")
        st.write("無制限利用可能")

def show_upgrade_modal():
    """アップグレードモーダル表示"""
    st.info("Premium機能：\n- 無制限OCR\n- 無制限質問\n- 高精度モデル利用")
    
def check_usage_limit(action_type):
    """使用制限チェック"""
    plan = st.session_state.user_plan
    
    if plan == 'premium':
        return True  # プレミアムは制限なし
    
    # 無料プランの制限チェック
    if action_type == 'ocr':
        count_key = 'ocr_usage_count'
        limit = 20
    elif action_type == 'question':
        count_key = 'question_usage_count'
        limit = 20
    else:
        return True
    
    current_count = st.session_state.get(count_key, 0)
    
    if current_count >= limit:
        st.error(f"{action_type.upper()}の使用回数上限に達しました。Premiumにアップグレードしてください。")
        return False
    
    return True

def increment_usage(action_type):
    """使用回数をインクリメントし、ファイルに保存"""
    user_id = st.session_state.user_info.get('sub')
    if not user_id:
        return

    plan = st.session_state.user_plan
    
    # 無料プランの場合のみカウント
    if plan == 'free':
        count_key = None
        if action_type == 'ocr':
            count_key = 'ocr_usage_count'
        elif action_type == 'question':
            count_key = 'question_usage_count'
        
        if count_key:
            # セッションのカウントを更新
            current_count = st.session_state.get(count_key, 0)
            st.session_state[count_key] = current_count + 1
            
            # ユーザーデータをロードして更新し、保存
            user_data = load_user_data(user_id)
            user_data[count_key] = st.session_state[count_key]
            # 最終利用日時を更新
            user_data['last_usage_time'] = datetime.now().isoformat()
            save_user_data(user_id, user_data)
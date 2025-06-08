# -*- coding: utf-8 -*-
import streamlit as st
import os
import tempfile
import shutil
from PIL import Image
import subprocess
import openai
import google.generativeai as genai
import base64
import cv2
import numpy as np
import io
from dotenv import load_dotenv

# 認証・課金モジュールをインポート
from auth import (
    init_auth_session, login_required, show_login_page, 
    handle_oauth_callback, show_user_info, check_usage_limit, 
    increment_usage, sync_subscription_status, logout
)
from payment import (
    show_pricing_page, handle_payment_callback, 
    init_payment_session, verify_premium_access,
    manage_subscription
)

# 環境変数読み込み
load_dotenv()

# Gemini API設定
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# ページ設定
st.set_page_config(
    page_title="RigakuGPT",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# カスタムCSS
st.markdown("""
<style>
    .main > div {
        padding-top: 2rem;
    }
    .stApp > header {
        background-color: transparent;
    }
    .css-18e3th9 {
        padding-top: 1rem;
        padding-bottom: 1rem;
    }
    h1 {
        color: #1f77b4;
        font-family: 'Arial', sans-serif;
        text-align: center;
        margin-bottom: 2rem;
    }
    h2 {
        color: #2c3e50;
        border-bottom: 2px solid #3498db;
        padding-bottom: 0.5rem;
    }
    .stButton > button {
        width: 100%;
        border-radius: 20px;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: 600;
        transition: all 0.3s;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
</style>
""", unsafe_allow_html=True)

def main():
    # 認証・課金セッションの初期化
    init_auth_session()
    init_payment_session()
    
    # セッション状態の初期化
    if 'latex_code' not in st.session_state:
        st.session_state.latex_code = ""
    if 'pdf_path' not in st.session_state:
        st.session_state.pdf_path = None
    if 'ai_response' not in st.session_state:
        st.session_state.ai_response = ""
    
    # OAuth・支払いコールバック処理
    handle_oauth_callback()
    handle_payment_callback()
    
    # ログイン状態をチェック
    if not st.session_state.get("authenticated"):
        show_login_page()
        return

    # ログイン済みの場合、Stripeのサブスクリプション状態を同期
    user_id = st.session_state.user_info.get("sub")
    user_email = st.session_state.user_info.get("email")
    if user_id and user_email:
        sync_subscription_status(user_id, user_email)
    
    # タブ設定
    tab1, tab2 = st.tabs(["💬 メイン", "👤 ユーザー情報"])
    
    with tab1:
        # ヘッダー
        st.markdown("""
        <div style="text-align: center; padding: 2rem 0;">
            <h1 style="color: white;">RigakuGPT</h1>
        </div>
        """, unsafe_allow_html=True)
        
        # 認証チェック
        if not st.session_state.get('authenticated', False):
            show_login_page()
            return
        
        # プラン情報をメイン画面上部に表示
        show_plan_info_main()
        
        # メインコンテンツ
        show_main_content()
    
    with tab2:
        # ユーザー情報・設定タブ
        show_user_tab()
    
def show_plan_info_main():
    """メイン画面上部にプラン情報を表示"""
    if st.session_state.get('authenticated', False):
        user_info = st.session_state.user_info
        plan = st.session_state.user_plan
        
        # プラン表示
        plan_color = "#28a745" if plan == 'premium' else "#6c757d"
        plan_text = "Premium" if plan == 'premium' else "Free"
        
        # 使用状況の取得
        if plan == 'free':
            ocr_count = st.session_state.get('ocr_usage_count', 0)
            question_count = st.session_state.get('question_usage_count', 0)
            usage_text = f"OCR: {ocr_count}/20回 | 質問: {question_count}/20回 | 状態は1日でリセットされます。" 
        else:
            usage_text = "無制限利用可能"
        
        # プラン情報をコンパクトに表示
        st.markdown(f"""
        <div style="background-color: #f8f9fa; border-radius: 10px; padding: 1rem; margin-bottom: 1.5rem; border-left: 4px solid {plan_color};">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-weight: bold; color: {plan_color};">{plan_text}プラン</span>
                    <span style="margin-left: 1rem; color: #6c757d; font-size: 0.9rem;">{usage_text}</span>
                </div>
                <div style="color: #6c757d; font-size: 0.9rem;">
                    {user_info['email']}
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

def show_main_content():
    """メインコンテンツを表示"""
    # API キーの設定（環境変数から取得）
    if not os.environ.get("OPENAI_API_KEY"):
        st.error("OpenAI APIのエラー。管理者@ClashRoyale_Hまでご連絡お願いします。")
        st.stop()
    
    if not os.environ.get("GEMINI_API_KEY"):
        st.error("Gemini APIのエラー。管理者@ClashRoyale_Hまでご連絡お願いします。")
        st.stop()
    
    # 追加のセッション状態を初期化
    if 'additional_response' not in st.session_state:
        st.session_state.additional_response = ""
    if 'response_pdf_path' not in st.session_state:
        st.session_state.response_pdf_path = None
    if 'last_question' not in st.session_state:
        st.session_state.last_question = ""
    
    # 設定オプション（ページ上部）
    st.markdown("### 🤖 画像認識")
    st.info("画像から数式を認識します")
    
    st.markdown("### 📤 画像アップロード")
    # アップロードエリア（複数ファイル対応）
    uploaded_files = st.file_uploader(
        "📁 画像を選択（複数可）",
        type=['png', 'jpg', 'jpeg'],
        accept_multiple_files=True,
        help="質問したい内容を含む画像をアップロードしてください。"
    )
    enable_preprocessing = st.checkbox(
        "画像前処理を有効化",
        value=True,
        help="画像を処理し、見やすくします。"
    )
    
    if uploaded_files:
        # アップロードされた画像を表示
        st.markdown(f"**アップロード数:** {len(uploaded_files)}枚")
        
        # 前処理プレビュー用のコンテナ
        processed_images = []
        
        if enable_preprocessing:
            with st.spinner("🔧 画像前処理中..."):
                for uploaded_file in uploaded_files:
                    processed_img, success = preprocess_image(uploaded_file)
                    processed_images.append(processed_img)
                    if not success:
                        st.warning(f"{uploaded_file.name} の前処理に失敗しました")
        
        # 画像表示（前処理が有効な場合は前処理済みのみ、無効な場合は元画像のみ）
        if enable_preprocessing and processed_images:
            # 前処理済み画像のみ表示
            if len(uploaded_files) == 1:
                st.image(processed_images[0], use_column_width=True)
            else:
                cols = st.columns(min(len(uploaded_files), 3))
                for i, (uploaded_file, processed_img) in enumerate(zip(uploaded_files, processed_images)):
                    with cols[i % 3]:
                        st.image(processed_img, use_column_width=True)
        else:
            # 前処理なしの場合は元画像のみ表示
            if len(uploaded_files) == 1:
                image = Image.open(uploaded_files[0])
                st.image(image, use_column_width=True)
            else:
                cols = st.columns(min(len(uploaded_files), 3))
                for i, uploaded_file in enumerate(uploaded_files):
                    with cols[i % 3]:
                        image = Image.open(uploaded_file)
                        st.image(image, use_column_width=True)
        
        # OCR 実行ボタン
        if st.button("🔍 この文章を読み込む", type="primary"):
            # 使用制限チェック
            if not check_usage_limit('ocr'):
                return
            
            with st.spinner(f"{len(uploaded_files)}枚の画像を読み取り中..."):
                # プランに応じてOCRモデルを選択
                if st.session_state.user_plan == 'premium':
                    ocr_model = "gpt-4o"  # Premiumユーザーは高性能モデル
                else:
                    ocr_model = "gpt-4o-mini"  # Freeユーザーは標準モデル

                # 前処理が有効な場合は前処理済み画像を使用
                if enable_preprocessing and processed_images:
                    latex_result = perform_ocr_with_processed_images(processed_images, uploaded_files, model=ocr_model)
                else:
                    latex_result = perform_ocr_with_multiple_images(uploaded_files, model=ocr_model)
                    
                if latex_result:
                    st.session_state.latex_code = latex_result
                    # 使用回数をインクリメント
                    increment_usage('ocr')
                    st.success("✅ 読み取り完了!")
                    
                    # 認識結果を表示（生のTeX + レンダリング済み）
                    st.markdown("### 📄 認識結果")
                    render_latex_content(latex_result)
                    
                else:
                    st.error("❌ 読み取りに失敗しました")
            
    else:
        # 画像がアップロードされていない場合のみ表示
        st.info("質問したい部分の画像をアップロードしてください（複数枚可）")
        
        # 手動入力ボタン
        if st.button("📝 TeXを手動で入力"):
            st.session_state.latex_code = ""
            st.info("TeX手動入力し、質問ができます")
    
    # テスト用クイック入力（画像がない場合のみ表示）
    if not uploaded_files:
        with st.expander("🧪 テスト用の数式で試す"):
            col_test1, col_test2 = st.columns([1, 1])
            with col_test1:
                if st.button("二次方程式について知りたい"):
                    st.session_state.latex_code = "二次方程式の解の公式\n\n$$x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$$\n\nここで、$a$, $b$, $c$ は係数である。"
            with col_test2:
                if st.button("積分について知りたい"):
                    st.session_state.latex_code = "定積分の基本定理\n\n$$\\int_a^b f(x) dx = F(b) - F(a)$$\n\nただし、$F(x)$ は $f(x)$ の原始関数である。"

    st.markdown("### 📝 テキスト編集 & PDF生成")
    
    latex_code = st.text_area(
        "📄 認識に誤りがある場合はここで編集することができます",
        value=st.session_state.get('latex_code', ''),
        height=250,
        help="認識された内容を確認・編集してください",
        placeholder="ここに認識されたテキスト・数式が表示されます..."
    )
    
    if latex_code != st.session_state.get('latex_code', ''):
        st.session_state.latex_code = latex_code
    
    # PDF 生成ボタン
    if st.button("📄 入力をPDFで確認する", disabled=not latex_code):
        with st.spinner("📄 PDF生成中..."):
            pdf_path = generate_pdf(latex_code)
            if pdf_path:
                st.session_state.pdf_path = pdf_path
                st.success("✅ PDF生成完了!")
            else:
                st.error("❌ PDF生成失敗")
    
    # PDF プレビュー表示
    pdf_path = st.session_state.get('pdf_path')
    if pdf_path and os.path.exists(pdf_path):
        st.header("📄 PDF")
        
        # PDF を Base64 エンコードして表示
        with open(pdf_path, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        
        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="500" type="application/pdf"></iframe>'
        st.markdown(pdf_display, unsafe_allow_html=True)

    # --- シンプルで安定したチャットUI ---
    st.markdown("---")
    st.markdown("### 💬 チャット")
    
    # モデルの表示名
    MODEL_DISPLAY_NAMES = {
        "gemini-1.5-flash-latest": "⚡ 高速な応答に最適",
        "gpt-4o-mini": "🤖 バランスの取れた性能",
        "gemini-1.5-pro-latest": "🧠 高度な推論に最適"
    }
    
    # チャットモデル選択（プレミアムユーザーのみ）
    chat_model = "gemini-1.5-flash-latest"  # 無料プランのデフォルト
    if st.session_state.user_plan == 'premium':
        chat_model = st.selectbox(
            "🤖 チャットモデルを選択",
            options=list(MODEL_DISPLAY_NAMES.keys()),
            format_func=lambda model_id: MODEL_DISPLAY_NAMES[model_id],
            help="Premium: 高性能なモデルを選択できます",
            index=0
        )
    else:
        st.info(f"🔥{MODEL_DISPLAY_NAMES['gemini-1.5-flash-latest']}な推論モデルを使用してチャットします。")

    # チャットメッセージの初期化
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # チャット履歴の表示
    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            render_latex_content(message["content"])

    # ユーザーからの入力を受け取る
    if prompt := st.chat_input("数式について質問・追加質問してください..."):
        # latex_codeがなければ何もしない
        if not st.session_state.get('latex_code'):
            st.warning("まず、上のセクションで数式を含む画像をアップロードまたはテキストを入力してください。")
            st.stop()
        
        # ユーザーのメッセージを履歴に追加 & 表示
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            render_latex_content(prompt)

        # 使用制限チェック & AI応答
        if not check_usage_limit('question'):
             # 制限超過メッセージをチャットに追加 & 表示
            limit_msg = "無料プランの質問回数上限に達しました。ユーザー情報タブからPremiumプランへのアップグレードをご検討ください。"
            st.session_state.chat_messages.append({"role": "assistant", "content": limit_msg})
            with st.chat_message("assistant"):
                render_latex_content(limit_msg)
        else:
            # AIからの応答を生成 & 表示
            with st.chat_message("assistant"):
                with st.spinner("🤖 AIが回答を生成中..."):
                    context = build_chat_context(st.session_state.chat_messages, st.session_state.latex_code)
                    
                    # 選択されたモデルに応じて応答を生成
                    if chat_model.startswith("gemini"):
                        response = get_gemini_response(context, chat_model)
                    else:  # gpt-4o-mini
                        response = get_ai_response_simple(context)
                
                    if response:
                        render_latex_content(response)
                        # 応答を履歴に追加
                        st.session_state.chat_messages.append({"role": "assistant", "content": response})
                        increment_usage('question')
                    else:
                        error_msg = "申し訳ありません、エラーが発生しました。"
                        render_latex_content(error_msg)
                        st.session_state.chat_messages.append({"role": "assistant", "content": error_msg})

    # チャット履歴がある場合の補助ボタン
    if st.session_state.get('chat_messages'):
        st.markdown("---")
        
        if st.button("🗑️ チャットをリセット", use_container_width=True):
            st.session_state.chat_messages = []
            st.rerun()
        
        if st.button("📄 会話をPDFで出力", use_container_width=True):
            with st.spinner("📄 PDF生成中..."):
                pdf_path = generate_conversation_pdf(st.session_state.chat_messages, st.session_state.get('latex_code', ''))
                if pdf_path:
                    st.session_state.response_pdf_path = pdf_path
                    st.success("✅ PDF生成完了!")
                else:
                    st.error("❌ PDF生成失敗")
        
        if st.session_state.get('response_pdf_path'):
            with open(st.session_state.response_pdf_path, "rb") as pdf_file:
                st.download_button(
                    label="💾 PDFダウンロード",
                    data=pdf_file.read(),
                    file_name="rigakugpt_conversation.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

def show_user_tab():
    """ユーザー情報・設定タブを表示"""
    st.markdown("# 👤 ユーザー情報")
    
    if st.session_state.get('authenticated', False):
        user_info = st.session_state.user_info
        plan = st.session_state.user_plan
        
        # ユーザー情報表示（名前は除外）
        col1, col2 = st.columns([1, 3])
        
        with col1:
            if user_info.get('picture'):
                st.image(user_info['picture'], width=100)
        
        with col2:
            st.markdown(f"**Email:** {user_info['email']}")
            
            # プラン表示
            plan_color = "#28a745" if plan == 'premium' else "#6c757d"
            plan_text = "Premium" if plan == 'premium' else "Free"
            st.markdown(f"**プラン:** <span style='color: {plan_color}; font-weight: bold;'>{plan_text}</span>", 
                       unsafe_allow_html=True)
        
        # 使用制限表示
        if plan == 'free':
            # 使用回数を取得
            ocr_count = st.session_state.get('ocr_usage_count', 0)
            question_count = st.session_state.get('question_usage_count', 0)
            
            st.markdown("---")
            st.markdown("### 📊 使用状況")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("OCR実行", f"{ocr_count}回")
            with col2:
                st.metric("質問回数", f"{question_count}回")
        else:
            st.markdown("---")
            st.markdown("### ⭐ Premium")
            st.success("無制限利用可能")
        
        # 料金プラン表示
        st.markdown("---")
        show_pricing_page()
        
        # ログアウトボタン
        st.markdown("---")
        if st.button("🚪 ログアウト", use_container_width=True, type="secondary"):
            logout()
    else:
        st.warning("ログインが必要です")

def preprocess_image(image_file):
    """
    教科書画像の前処理：コントラスト強化 + 彩度削除
    """
    try:
        # PILからOpenCV形式に変換
        pil_image = Image.open(image_file)
        
        # RGBに変換（必要に応じて）
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')
        
        # numpy配列に変換
        image_array = np.array(pil_image)
        
        # BGRからRGBに変換（OpenCV用）
        image_bgr = cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR)
        
        # 1. 彩度を削除（グレースケール化）
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        
        # 2. コントラスト強化（グレースケール画像に対してCLAHE適用）
        clahe = cv2.createCLAHE(clipLimit=1.3, tileGridSize=(8, 8))
        enhanced_gray = clahe.apply(gray)
        
        # 3. グレースケール画像をRGBに戻す（3チャンネル）
        final_bgr = cv2.cvtColor(enhanced_gray, cv2.COLOR_GRAY2BGR)
        final_rgb = cv2.cvtColor(final_bgr, cv2.COLOR_BGR2RGB)
        
        # PIL Imageに変換
        processed_image = Image.fromarray(final_rgb)
        
        return processed_image, True
        
    except Exception as e:
        st.warning(f"画像前処理でエラーが発生しました: {str(e)}")
        # エラーの場合は元の画像を返す
        return Image.open(image_file), False

def render_latex_content(text):
    """LaTeX混在テキストをStreamlitでレンダリング（シンプル版）"""
    try:
        # 空文字チェック
        if not text or not text.strip():
            st.warning("認識されたテキストが空です")
            return
        
        # st.markdownはLaTeX（KaTeX）を直接サポートしているため、
        # テキストをそのまま渡すだけで良い
        st.markdown(text, unsafe_allow_html=True)
                    
    except Exception as e:
        st.error(f"レンダリングエラー: {str(e)}")
        # エラー時でも、元のテキストを極力表示しようと試みる
        st.markdown("**フォールバック表示:**")
        st.text(text)

def perform_ocr_with_processed_images(processed_images, original_files, model="gpt-4o-mini"):
    """前処理済み画像からGPT Visionを使用して全ての文字・数式を抽出"""
    try:
        # 複数画像のbase64エンコード
        image_contents = []
        
        for i, (processed_img, original_file) in enumerate(zip(processed_images, original_files)):
            # PIL ImageをBytesIOに変換
            img_buffer = io.BytesIO()
            processed_img.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            
            # base64エンコード
            image_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
            
            image_contents.append({
                "type": "image_url", 
                "image_url": {
                    "url": f"data:image/png;base64,{image_base64}",
                    "detail": "high"
                }
            })
        
        # OpenAI クライアントを作成
        client = openai.OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            default_headers={}  # カスタムヘッダーをクリア
        )
        
        # メッセージ構築（前処理済み画像対応）
        content = [
            {
                "type": "text",
                "text": f"これら{len(processed_images)}枚の前処理済み画像に含まれる全ての文字・数式を正確に読み取って、正確に書き出してください。数式はLaTeX記法で表現してください。これらの画像は読み取りやすくするために前処理（コントラスト強化、ノイズ除去等）が施されています。複数の画像がある場合は、順番に内容を統合して1つの文書として出力してください。"
            }
        ]
        content.extend(image_contents)
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": """あなたは高精度なOCRシステムです。前処理済みの画像から全ての文字・数式を正確に読み取ってください。

                以下のルールに従ってください：
                1. 前処理によりコントラストが強化され、文字が鮮明になっています
                2. 数式は適切なLaTeX記法で表現する（\\frac, \\sum, \\int, \\sqrt など）
                3. 通常のテキストはそのまま記述する
                4. レイアウト（段落、改行）を可能な限り保持する
                5. 数式とテキストを適切に区別する
                6. インライン数式は $ $ で、ディスプレイ数式は $$ $$ で囲む
                7. 前処理により文字境界が強調されているので、細かい記号や上付き・下付き文字も正確に読み取る

                出力例：
                「三角関数の公式
                $\\sin^2 x + \\cos^2 x = 1$
                これは三角関数の最も基本的な恒等式である。

                微分の定義
                $$\\frac{d}{dx} f(x) = \\lim_{h \\to 0} \\frac{f(x+h) - f(x)}{h}$$」"""
                },
                {
                    "role": "user",
                    "content": content
                }
            ],
            max_tokens=3000  # 複数画像なので上限を増やす
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        error_msg = str(e).encode('utf-8', errors='ignore').decode('utf-8')
        st.error(f"前処理済み画像 OCR エラー: {error_msg}")
        st.error(f"エラー詳細: {type(e).__name__}")
        # デバッグ情報
        st.write("API キー設定状況:", "設定済み" if os.environ.get("OPENAI_API_KEY") else "未設定")
        st.write("ファイル数:", len(uploaded_files) if uploaded_files else 0)
        return None

def perform_ocr_with_gemini_processed_images(processed_images, original_files):
    """前処理済み画像からGemini 1.5 Flashを使用して全ての文字・数式を抽出"""
    try:
        # Gemini 1.5 Flash モデルを使用
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        # 前処理済み画像をGemini用に準備
        gemini_images = []
        for processed_img in processed_images:
            # PIL ImageをBytesIOに変換
            img_buffer = io.BytesIO()
            processed_img.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            
            # Gemini用の画像オブジェクトを作成
            gemini_images.append({
                'mime_type': 'image/png',
                'data': img_buffer.getvalue()
            })
        
        # プロンプトを作成
        prompt = f"""これら{len(processed_images)}枚の前処理済み画像に含まれる全ての文字・数式を正確に読み取って、正確に書き出してください。

以下のルールに従ってください：
1. 前処理によりコントラストが強化され、文字が鮮明になっています
2. 数式は適切なLaTeX記法で表現する（\\frac, \\sum, \\int, \\sqrt など）
3. 通常のテキストはそのまま記述する
4. レイアウト（段落、改行）を可能な限り保持する
5. 数式とテキストを適切に区別する
6. インライン数式は $ $ で、ディスプレイ数式は $$ $$ で囲む
7. 複数の画像がある場合は、順番に内容を統合して1つの文書として出力してください

出力例：
「三角関数の公式
$\\sin^2 x + \\cos^2 x = 1$
これは三角関数の最も基本的な恒等式である。

微分の定義
$$\\frac{{d}}{{dx}} f(x) = \\lim_{{h \\to 0}} \\frac{{f(x+h) - f(x)}}{{h}}$$」
"""
        
        # リクエストの内容を構築
        request_parts = [prompt]
        for img in gemini_images:
            request_parts.append(img)
        
        # Gemini APIを呼び出し
        response = model.generate_content(request_parts)
        
        return response.text.strip()
        
    except Exception as e:
        error_msg = str(e).encode('utf-8', errors='ignore').decode('utf-8')
        st.error(f"Gemini OCR エラー: {error_msg}")
        st.error(f"エラー詳細: {type(e).__name__}")
        return None

def perform_ocr_with_gemini_multiple_images(uploaded_files):
    """複数の画像からGemini 1.5 Flashを使用して全ての文字・数式を抽出"""
    try:
        # Gemini 1.5 Flash モデルを使用
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        # 画像をGemini用に準備
        gemini_images = []
        for uploaded_file in uploaded_files:
            # ファイル形式を判定
            file_type = uploaded_file.type
            if file_type == "image/jpeg":
                mime_type = "image/jpeg"
            elif file_type == "image/png":
                mime_type = "image/png"
            elif file_type == "image/webp":
                mime_type = "image/webp"
            else:
                mime_type = "image/png"  # デフォルト
            
            gemini_images.append({
                'mime_type': mime_type,
                'data': uploaded_file.getvalue()
            })
        
        # プロンプトを作成
        prompt = f"""これら{len(uploaded_files)}枚の画像に含まれる全ての文字・数式を正確に読み取って、正確に書き出してください。

以下のルールに従ってください：
1. 画像の全ての文字を漏れなく抽出する
2. 数式は適切なLaTeX記法で表現する（\\frac, \\sum, \\int, \\sqrt など）
3. 通常のテキストはそのまま記述する
4. レイアウト（段落、改行）を可能な限り保持する
5. 数式とテキストを適切に区別する
6. インライン数式は $ $ で、ディスプレイ数式は $$ $$ で囲む
7. 複数の画像がある場合は、順番に内容を統合して1つの文書として出力してください

出力例：
「三角関数の公式
$\\sin^2 x + \\cos^2 x = 1$
これは三角関数の最も基本的な恒等式である。

微分の定義
$$\\frac{{d}}{{dx}} f(x) = \\lim_{{h \\to 0}} \\frac{{f(x+h) - f(x)}}{{h}}$$」
"""
        
        # リクエストの内容を構築
        request_parts = [prompt]
        for img in gemini_images:
            request_parts.append(img)
        
        # Gemini APIを呼び出し
        response = model.generate_content(request_parts)
        
        return response.text.strip()
        
    except Exception as e:
        error_msg = str(e).encode('utf-8', errors='ignore').decode('utf-8')
        st.error(f"Gemini OCR エラー: {error_msg}")
        st.error(f"エラー詳細: {type(e).__name__}")
        return None

def perform_ocr_with_multiple_images(uploaded_files, model="gpt-4o-mini"):
    """複数の画像からGPT Visionを使用して全ての文字・数式を抽出"""
    try:
        # 複数画像のbase64エンコード
        image_contents = []
        
        for i, uploaded_file in enumerate(uploaded_files):
            image_base64 = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
            
            # ファイル形式を判定
            file_type = uploaded_file.type
            if file_type == "image/jpeg":
                mime_type = "image/jpeg"
            elif file_type == "image/png":
                mime_type = "image/png"
            elif file_type == "image/webp":
                mime_type = "image/webp"
            else:
                mime_type = "image/png"  # デフォルト
            
            image_contents.append({
                "type": "image_url", 
                "image_url": {
                    "url": f"data:{mime_type};base64,{image_base64}",
                    "detail": "high"
                }
            })
        
        # OpenAI クライアントを作成
        client = openai.OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            default_headers={}  # カスタムヘッダーをクリア
        )
        
        # メッセージ構築（複数画像対応）
        content = [
            {
                "type": "text",
                "text": f"これら{len(uploaded_files)}枚の前処理済み画像に含まれる全ての文字・数式を正確に読み取って、正確に書き出してください。数式はLaTeX記法で表現してください。これらの画像は読み取りやすくするために前処理（コントラスト強化、ノイズ除去等）が施されています。複数の画像がある場合は、順番に内容を統合して1つの文書として出力してください。"
            }
        ]
        content.extend(image_contents)
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": """あなたは高精度なOCRシステムです。複数の画像に含まれる全ての文字・数式を正確に読み取ってください。

                以下のルールに従ってください：
                1. 前処理によりコントラストが強化され、文字が鮮明になっています
                2. 数式は適切なLaTeX記法で表現する（\\frac, \\sum, \\int, \\sqrt など）
                3. 通常のテキストはそのまま記述する
                4. レイアウト（段落、改行）を可能な限り保持する
                5. 数式とテキストを適切に区別する
                6. インライン数式は $ $ で、ディスプレイ数式は $$ $$ で囲む
                7. 前処理により文字境界が強調されているので、細かい記号や上付き・下付き文字も正確に読み取る

                出力例：
                「三角関数の公式
                $\\sin^2 x + \\cos^2 x = 1$
                これは三角関数の最も基本的な恒等式である。

                微分の定義
                $$\\frac{d}{dx} f(x) = \\lim_{h \\to 0} \\frac{f(x+h) - f(x)}{h}$$」"""
                },
                {
                    "role": "user",
                    "content": content
                }
            ],
            max_tokens=3000  # 複数画像なので上限を増やす
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        error_msg = str(e).encode('utf-8', errors='ignore').decode('utf-8')
        st.error(f"GPT Vision OCR エラー: {error_msg}")
        st.error(f"エラー詳細: {type(e).__name__}")
        # デバッグ情報
        st.write("API キー設定状況:", "設定済み" if os.environ.get("OPENAI_API_KEY") else "未設定")
        st.write("ファイル数:", len(uploaded_files) if uploaded_files else 0)
        return None

def perform_ocr_with_gpt(uploaded_file, model="gpt-4o-mini"):
    """GPT Vision を使用して画像から全ての文字・数式を抽出"""
    try:
        # 画像をbase64エンコード
        image_base64 = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
        
        # ファイル形式を判定
        file_type = uploaded_file.type
        if file_type == "image/jpeg":
            mime_type = "image/jpeg"
        elif file_type == "image/png":
            mime_type = "image/png"
        elif file_type == "image/webp":
            mime_type = "image/webp"
        else:
            mime_type = "image/png"  # デフォルト
        
        # OpenAI クライアントを作成
        client = openai.OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            default_headers={}  # カスタムヘッダーをクリア
        )
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": """枚の前処理済み画像に含まれる全ての文字・数式を正確に読み取って、正確に書き出してください。数式はLaTeX記法で表現してください。これらの画像は読み取りやすくするために前処理（コントラスト強化、ノイズ除去等）が施されています。

                以下のルールに従ってください：
                1. 画像の全ての文字を漏れなく抽出する
                2. 数式は適切なLaTeX記法で表現する（\\frac, \\sum, \\int, \\sqrt など）
                3. 通常のテキストはそのまま記述する
                4. レイアウト（段落、改行）を可能な限り保持する
                5. 数式とテキストを適切に区別する
                6. インライン数式は $ $ で、ディスプレイ数式は $$ $$ で囲む

                出力例：
                「三角関数の公式

                $\\sin^2 x + \\cos^2 x = 1$

                これは三角関数の最も基本的な恒等式である。」"""
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "この画像に含まれる全ての文字・数式を正確に読み取って、適切にフォーマットしてください。数式はLaTeX記法で表現してください。"
                        },
                        {
                            "type": "image_url", 
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_base64}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=2000
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        error_msg = str(e).encode('utf-8', errors='ignore').decode('utf-8')
        st.error(f"GPT Vision OCR エラー: {error_msg}")
        st.error(f"エラー詳細: {type(e).__name__}")
        # デバッグ情報
        st.write("API キー設定状況:", "設定済み" if os.environ.get("OPENAI_API_KEY") else "未設定")
        st.write("ファイルタイプ:", uploaded_file.type if hasattr(uploaded_file, 'type') else "不明")
        return None

def generate_pdf(latex_code):
    """LaTeX コードから PDF を生成"""
    try:
        # エンコーディング安全化（日本語対応）
        safe_latex_code = str(latex_code).encode('utf-8', errors='ignore').decode('utf-8')
        
        # LaTeX ドキュメントテンプレート（uplatex + 日本語対応）
        latex_document = f"""
\\documentclass[12pt,a4paper,uplatex]{{jsarticle}}
\\usepackage{{amsmath}}
\\usepackage{{amsfonts}}
\\usepackage{{amssymb}}
\\usepackage{{geometry}}
\\geometry{{margin=2cm}}

\\begin{{document}}

\\begin{{center}}
{{\\Large \\textbf{{rigakuGPT - 数式プレビュー}}}}
\\end{{center}}

\\vspace{{1cm}}

{safe_latex_code}

\\vfill
\\begin{{flushright}}
\\textit{{Generated by rigakuGPT}}
\\end{{flushright}}

\\end{{document}}
"""
        
        # 一時ディレクトリで PDF 生成
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = os.path.join(tmpdir, "document.tex")
            
            # UTF-8で安全に書き込み
            try:
                with open(tex_path, 'w', encoding='utf-8', errors='ignore') as f:
                    f.write(latex_document)
            except UnicodeEncodeError:
                # フォールバック: ASCII文字のみで書き込み
                ascii_document = latex_document.encode('ascii', errors='ignore').decode('ascii')
                with open(tex_path, 'w', encoding='ascii') as f:
                    f.write(ascii_document)
            
            # uplatex + dvipdfmxでコンパイル（手動実行）
            # Step 1: uplatex で .dvi ファイル生成
            try:
                result1 = subprocess.run([
                    'uplatex', 
                    '-interaction=nonstopmode',
                    '-halt-on-error',
                    'document.tex'
                ], cwd=tmpdir, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                
                if result1.returncode != 0:
                    st.error("uplatex コンパイルエラー:")
                    st.code(f"stdout: {result1.stdout}")
                    st.code(f"stderr: {result1.stderr}")
                    return None
                
                # Step 2: dvipdfmx で .pdf ファイル生成
                result2 = subprocess.run([
                    'dvipdfmx', 
                    'document.dvi'
                ], cwd=tmpdir, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                
                if result2.returncode != 0:
                    st.error("dvipdfmx コンパイルエラー:")
                    st.code(f"stdout: {result2.stdout}")
                    st.code(f"stderr: {result2.stderr}")
                    return None
                
                pdf_path = os.path.join(tmpdir, "document.pdf")
                
                if os.path.exists(pdf_path):
                    # PDF を保存用ディレクトリにコピー
                    output_dir = "outputs"
                    os.makedirs(output_dir, exist_ok=True)
                    final_pdf_path = os.path.join(output_dir, "preview.pdf")
                    shutil.copy2(pdf_path, final_pdf_path)
                    return final_pdf_path
                else:
                    st.error("PDF ファイルが生成されませんでした")
                    return None
                    
            except FileNotFoundError as e:
                st.error(f"LaTeX コンパイラが見つかりません: {str(e)}")
                st.info("uplatex と dvipdfmx がインストールされているか確認してください")
                return None
                
    except Exception as e:
        st.error(f"PDF 生成エラー: {str(e)}")
        return None

def build_conversation_context(chat_history, latex_code, new_question):
    """会話履歴を含むコンテキストを構築"""
    context = f"参考資料:\n{latex_code}\n\n"
    
    if chat_history:
        context += "これまでの会話履歴:\n"
        for i, (q, a) in enumerate(chat_history[-3:]):  # 最近の3つの会話のみ使用
            context += f"質問{i+1}: {q}\n回答{i+1}: {a}\n\n"
    
    context += f"新しい質問: {new_question}"
    return context

def build_conversation_context_from_messages(chat_messages, latex_code):
    """チャットメッセージ形式から会話履歴を含むコンテキストを構築"""
    context = f"参考資料:\n{latex_code}\n\n"
    
    if len(chat_messages) > 1:
        context += "これまでの会話履歴:\n"
        # 最新の質問を除いた最近の3組の会話のみ使用
        previous_messages = chat_messages[:-1]  # 最新のメッセージを除く
        recent_messages = previous_messages[-6:]  # 最大6メッセージ（3組）
        
        conversation_pairs = []
        for i in range(0, len(recent_messages), 2):
            if i + 1 < len(recent_messages):
                user_msg = recent_messages[i]["content"]
                ai_msg = recent_messages[i + 1]["content"]
                conversation_pairs.append((user_msg, ai_msg))
        
        for i, (q, a) in enumerate(conversation_pairs):
            context += f"質問{i+1}: {q}\n回答{i+1}: {a}\n\n"
    
    # 最新の質問を追加
    if chat_messages:
        latest_question = chat_messages[-1]["content"]
        context += f"新しい質問: {latest_question}"
    
    return context

def get_ai_response_with_context(conversation_context):
    """会話履歴を考慮したAI応答取得"""
    try:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            st.error("OpenAI API キーが設定されていません")
            return None
        
        client = openai.OpenAI(
            api_key=api_key,
            default_headers={}
        )
        
        response = client.chat.completions.create(
            model="o4-mini",
            messages=[
                {
                    "role": "system",
                    "content": """あなたは科学の専門家です。会話履歴を踏まえて、一貫性のある回答をしてください。

回答する際の重要なルール：
1. 会話履歴を考慮して、前の質問との関連性を意識する
2. 「先ほど」「前回」などの表現がある場合は、履歴を参照する
3. 数式は必ず正確なLaTeX記法で表現する
4. インライン数式は $...$ で囲む
5. ディスプレイ数式は $$...$$ で囲む
6. 追加質問の場合は、前の回答を踏まえて補足説明する
7. 一貫した説明を心がけ、矛盾のない回答をする
8. 回答は簡潔にまとめ、3-4段落以内に収める
9. ユーザーの入力に誤字脱字がある場合は、適切に解釈し、回答を行う

LaTeX記法の例：
- 分数: \\frac{分子}{分母}
- 上付き: x^{2}、下付き: x_{1}
- 平方根: \\sqrt{x}
- 積分: \\int_{下限}^{上限} f(x) dx
- 総和: \\sum_{i=1}^{n} a_i"""
                },
                {
                    "role": "user",
                    "content": conversation_context
                }
            ],
            max_tokens=600,
            temperature=0.7
        )
        
        result = response.choices[0].message.content
        return result
        
    except Exception as e:
        error_msg = str(e).encode('utf-8', errors='ignore').decode('utf-8')
        st.error(f"AI 応答エラー: {error_msg}")
        return None

def generate_conversation_pdf(chat_history, latex_code=""):
    """会話履歴をPDFとして出力"""
    try:
        def safe_encode(text):
            if isinstance(text, bytes):
                text = text.decode('utf-8', errors='ignore')
            
            # LaTeXの特殊文字をエスケープ
            # Note: バックスラッシュは最初に行う必要がある
            text = str(text).replace('\\', '\\textbackslash{}')
            text = text.replace('{', '\\{')
            text = text.replace('}', '\\}')
            text = text.replace('&', '\\&')
            text = text.replace('%', '\\%')
            text = text.replace('$', '\\$')
            text = text.replace('#', '\\#')
            text = text.replace('_', '\\_')
            text = text.replace('^', '\\textasciicircum{}')
            text = text.replace('~', '\\textasciitilde{}')
            # 角括弧をエスケープ
            text = text.replace('[', '{[}')
            text = text.replace(']', '{]}')

            return str(text).encode('utf-8', errors='ignore').decode('utf-8')
        
        # 会話内容を構築
        conversation_content = ""
        
        # chat_history (dictのリスト) を (質問, 回答) のペアに変換
        qa_pairs = []
        # 偶数番目がuser, 奇数番目がassistantであることを期待
        for i in range(0, len(chat_history) - 1, 2):
            if chat_history[i]['role'] == 'user' and chat_history[i+1]['role'] == 'assistant':
                qa_pairs.append((chat_history[i]['content'], chat_history[i+1]['content']))

        for i, (question, answer) in enumerate(qa_pairs):
            clean_question = clean_latex_for_pdf(safe_encode(question))
            clean_answer = clean_latex_for_pdf(safe_encode(answer))
            
            conversation_content += f"""
\\section*{{質問 {i+1}}}
\\begin{{quote}}
{clean_question}
\\end{{quote}}

\\subsection*{{回答}}
{clean_answer}

\\vspace{{1cm}}
"""
        
        clean_latex_code = clean_latex_for_pdf(safe_encode(latex_code)) if latex_code else "（参照内容なし）"
        
        latex_document = f"""
\\documentclass[12pt,a4paper,uplatex]{{jsarticle}}
\\usepackage{{amsmath}}
\\usepackage{{amsfonts}}
\\usepackage{{amssymb}}
\\usepackage{{geometry}}
\\usepackage{{graphicx}}
\\usepackage{{hyperref}}
\\geometry{{margin=2.5cm}}

\\title{{\\textbf{{rigakuGPT 会話レポート}}}}
\\author{{\\textsc{{rigakuGPT}}}}
\\date{{\\today}}

\\begin{{document}}

\\maketitle

\\section*{{参考資料}}
{clean_latex_code}

{conversation_content}

\\vfill
\\begin{{center}}
\\textbf{{rigakuGPT}}
\\end{{center}}

\\end{{document}}
"""
        
        # PDF生成処理
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = os.path.join(tmpdir, "conversation.tex")
            
            try:
                with open(tex_path, 'w', encoding='utf-8', errors='ignore') as f:
                    f.write(latex_document)
            except UnicodeEncodeError:
                ascii_document = latex_document.encode('ascii', errors='ignore').decode('ascii')
                with open(tex_path, 'w', encoding='ascii') as f:
                    f.write(ascii_document)
            
            # uplatex + dvipdfmxでコンパイル
            try:
                # Step 1: uplatex で .dvi ファイル生成
                result1 = subprocess.run([
                    'uplatex', 
                    '-interaction=nonstopmode',
                    '-halt-on-error',
                    'conversation.tex'
                ], cwd=tmpdir, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                
                if result1.returncode != 0:
                    st.error("会話PDF uplatex コンパイルエラー:")
                    st.text(f"stdout: {result1.stdout}")
                    st.text(f"stderr: {result1.stderr}")
                    return None
                
                # Step 2: dvipdfmx で .pdf ファイル生成
                result2 = subprocess.run([
                    'dvipdfmx', 
                    'conversation.dvi'
                ], cwd=tmpdir, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                
                if result2.returncode != 0:
                    st.error("会話PDF dvipdfmx エラー:")
                    st.text(f"stdout: {result2.stdout}")
                    st.text(f"stderr: {result2.stderr}")
                    return None
                
                pdf_path = os.path.join(tmpdir, "conversation.pdf")
                
                if os.path.exists(pdf_path):
                    # メモリに読み込んで返す
                    with open(pdf_path, 'rb') as f:
                        pdf_data = f.read()
                    
                    # 一時ファイルを削除させずに永続的なパスを返す
                    final_pdf_path = os.path.join(tempfile.gettempdir(), f"conversation_{os.urandom(8).hex()}.pdf")
                    with open(final_pdf_path, 'wb') as f:
                        f.write(pdf_data)
                    return final_pdf_path
                else:
                    st.error("生成されたPDFファイルが見つかりません。")
                    return None

            except FileNotFoundError:
                st.error("uplatex/dvipdfmxが見つかりません。TeX Liveがインストールされているか確認してください。")
                return None
            except Exception as e:
                st.error(f"PDF生成中に予期せぬエラーが発生しました: {e}")
                return None

    except Exception as e:
        st.error(f"PDF生成の準備中にエラー: {e}")
        return None

def get_ai_response_simple(context):
    """シンプルなAI応答取得（GPT-4o-miniなど）"""
    try:
        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": context['system_prompt']},
                {"role": "user", "content": context['user_input']}
            ],
            max_tokens=3000,
        )
        return response.choices[0].message.content
    except Exception as e:
        error_msg = str(e).encode('utf-8', errors='ignore').decode('utf-8')
        st.error(f"GPT 応答エラー: {error_msg}")
        return None

def get_gemini_response(context, model_name="gemini-1.5-flash-latest"):
    """Geminiモデルを使用して応答を取得"""
    try:
        # モデル設定
        if model_name == "gemini-1.5-flash-latest":
            # 無料プランは思考モード（中）を使用
            if st.session_state.user_plan == 'free':
                model = genai.GenerativeModel(
                    'gemini-1.5-flash-latest',
                    generation_config={
                    }
                )
            else:
                model = genai.GenerativeModel('gemini-1.5-flash-latest')
        elif model_name == "gemini-1.5-pro-latest":
            model = genai.GenerativeModel('gemini-1.5-pro-latest')
        else:
            model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        # システムプロンプト
        system_prompt = """あなたは科学の専門家です。会話履歴を踏まえて、一貫性のある回答をしてください。

回答する際の重要なルール：
1. 会話履歴を考慮して、前の質問との関連性を意識する
2. 「先ほど」「前回」などの表現がある場合は、履歴を参照する
3. 数式は必ず正確なLaTeX記法で表現する
4. インライン数式は $...$ で囲む
5. ディスプレイ数式は $$...$$ で囲む
6. 追加質問の場合は、前の回答を踏まえて補足説明する
7. 一貫した説明を心がけ、矛盾のない回答をする
8. 回答は簡潔にまとめ、3-4段落以内に収める
9. ユーザーの入力に誤字脱字がある場合は、適切に解釈し、回答を行う9. ユーザーの入力に誤字脱字がある場合は、適切に解釈し、回答を行う

LaTeX記法の例：
- 分数: \\frac{分子}{分母}
- 上付き: x^{2}、下付き: x_{1}
- 平方根: \\sqrt{x}
- 積分: \\int_{下限}^{上限} f(x) dx
- 総和: \\sum_{i=1}^{n} a_i"""
        
        # プロンプトを構築
        prompt = f"{system_prompt}\n\n{context}"
        
        # Gemini APIを呼び出し
        response = model.generate_content(prompt)
        
        return response.text.strip()
        
    except Exception as e:
        error_msg = str(e).encode('utf-8', errors='ignore').decode('utf-8')
        st.error(f"Gemini API エラー: {error_msg}")
        return None

def get_ai_response(latex_code, question):
    """GPT-4o mini に質問して回答を取得"""
    try:
        # OpenAI クライアントを作成
        client = openai.OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            default_headers={}  # カスタムヘッダーをクリア
        )
        
        response = client.chat.completions.create(
            model="o4-mini",
            messages=[
                {
                    "role": "system",
                    "content": """あなたは科学の専門家です。ユーザーから提供される数式・テキストについて、わかりやすく丁寧に解説してください。

回答する際の重要なルール：
1. 数式は必ず正確なLaTeX記法で表現する
2. インライン数式は $...$ で囲む
3. ディスプレイ数式は $$...$$ で囲む
4. LaTeX記法の例：
   - 分数: \\frac{分子}{分母}
   - 上付き: x^{2}、下付き: x_{1}
   - 平方根: \\sqrt{x}
   - 積分: \\int_{下限}^{上限} f(x) dx
   - 総和: \\sum_{i=1}^{n} a_i
   - ギリシャ文字: \\alpha, \\beta, \\gamma など
   - 関数: \\sin, \\cos, \\log, \\ln など
5. 数式を含む文章では、数式部分のみLaTeX記法を使用
6. 数学的に正確で初学者にもわかりやすい説明
7. 回答は簡潔にまとめ、3-4段落以内に収める
8. ユーザーの入力に誤字脱字がある場合は、適切に解釈し、回答を行う

出力例：
「この式 $f(x) = ax^2 + bx + c$ は二次関数を表しています。
解の公式は以下のようになります：
$$x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$$」"""
                },
                {
                    "role": "user",
                    "content": f"""以下のテキスト・数式について質問があります：

内容:
{latex_code}

質問:
{question}

この内容について詳しく教えてください。数式は正確なLaTeX記法で表現してください。"""
                }
            ],
            max_tokens=600,
            temperature=0.7
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        error_msg = str(e).encode('utf-8', errors='ignore').decode('utf-8')
        st.error(f"AI 応答エラー: {error_msg}")
        return None

def clean_latex_for_pdf(text):
    """AIの回答からLaTeX用に文字列をクリーニング（シンプルで堅牢なバージョン）"""
    import re
    
    try:
        if isinstance(text, bytes):
            text = text.decode('utf-8', errors='ignore')
        elif isinstance(text, str):
            text = text.encode('utf-8', errors='ignore').decode('utf-8')
        
        # 数式ブロックを保護 ($$...$$ と $...$)
        math_blocks = []
        def protect_math_block(match):
            placeholder = f"PLACEHOLDERMATHBLOCK{len(math_blocks)}"
            math_blocks.append(match.group(0))
            return placeholder
        
        text = re.sub(r'\$\$.*?\$\$', protect_math_block, text, flags=re.DOTALL)
        text = re.sub(r'\$[^$]*?\$', protect_math_block, text)

        # LaTeXの特殊文字を最小限エスケープ
        # \, {, } は数式やコマンドで使われるため、ここではエスケープしない
        escape_map = {
            '&': r'\\&',
            '%': r'\\%',
            '#': r'\\#',
            '_': r'\\_',
        }
        
        for old, new in escape_map.items():
            text = text.replace(old, new)
        
        # マークダウンのボールドとイタリック
        text = re.sub(r'\*\*(.*?)\*\*', r'\\textbf{\1}', text)
        text = re.sub(r'\*(.*?)\*', r'\\textit{\1}', text)

        # 改行を適切に処理
        text = text.replace('\n', '\\\\ \n')

        # 数式ブロックを復元
        for i, math in enumerate(math_blocks):
            text = text.replace(f"PLACEHOLDERMATHBLOCK{i}", math)
            
        return text
        
    except Exception as e:
        st.warning(f"PDF用のテキストクリーニングに失敗しました: {e}")
        # フォールバックとして、極力安全なテキストを返す
        return str(text).replace('&', '').replace('%', '').replace('#', '').replace('_', '')

def generate_response_pdf_safe(question, answer, latex_code=""):
    """安全な質問と回答のPDF生成（エラーハンドリング強化）"""
    try:
        return generate_response_pdf(question, answer, latex_code)
    except Exception as e:
        st.error(f"PDF生成エラー: {str(e)}")
        return None

def build_chat_context(chat_messages, latex_code):
    """チャット用のコンテキストを構築"""
    context = f"参考資料:\n{latex_code}\n\n"
    
    if len(chat_messages) > 1:
        context += "これまでの会話履歴:\n"
        # 最新のメッセージを除いた最近の会話を取得
        recent_messages = chat_messages[-6:]  # 最大6メッセージ（3組）
        
        for i in range(0, len(recent_messages) - 1, 2):
            if i + 1 < len(recent_messages):
                user_msg = recent_messages[i]["content"]
                ai_msg = recent_messages[i + 1]["content"]
                context += f"質問{i//2+1}: {user_msg}\n回答{i//2+1}: {ai_msg}\n\n"
    
    # 最新の質問を追加
    if chat_messages:
        latest_question = chat_messages[-1]["content"]
        context += f"新しい質問: {latest_question}"
    
    return context

def generate_response_pdf(question, answer, latex_code=""):
    """質問と回答をPDFとして出力"""
    try:
        # 安全にエンコーディングを処理
        def safe_encode(text):
            if isinstance(text, bytes):
                text = text.decode('utf-8', errors='ignore')
            return str(text).encode('utf-8', errors='ignore').decode('utf-8')
        
        # 文字列をクリーニング（日本語対応）
        clean_question = safe_encode(question)
        clean_answer = clean_latex_for_pdf(safe_encode(answer))  # AI回答は特殊文字処理が必要
        clean_latex_code = safe_encode(latex_code) if latex_code else "（参照内容なし）"
        
        # LaTeX ドキュメントテンプレート（uplatex + 日本語対応）
        latex_document = """
\\documentclass[12pt,a4paper,uplatex]{jsarticle}
\\usepackage{amsmath}
\\usepackage{amsfonts}
\\usepackage{amssymb}
\\usepackage{geometry}
\\geometry{margin=2.5cm}

\\title{\\textbf{回答}}
\\author{\\textsc{rigakuGPT}}
\\date{\\today}

\\begin{document}

\\maketitle

\\section{質問}
\\begin{quote}
""" + clean_question + """
\\end{quote}

\\section{参考資料}
""" + clean_latex_code + """

\\section{回答}
""" + clean_answer + """

\\vfill
\\begin{center}
\\textbf{rigakuGPT}
\\end{center}

\\end{document}
"""
        
        # 一時ディレクトリで PDF 生成
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = os.path.join(tmpdir, "response.tex")
            
            # UTF-8で安全に書き込み
            try:
                with open(tex_path, 'w', encoding='utf-8', errors='ignore') as f:
                    f.write(latex_document)
            except UnicodeEncodeError:
                # フォールバック: ASCII文字のみで書き込み
                ascii_document = latex_document.encode('ascii', errors='ignore').decode('ascii')
                with open(tex_path, 'w', encoding='ascii') as f:
                    f.write(ascii_document)
            
            # uplatex + dvipdfmxでコンパイル（手動実行）
            try:
                # Step 1: uplatex で .dvi ファイル生成
                result1 = subprocess.run([
                    'uplatex', 
                    '-interaction=nonstopmode',
                    '-halt-on-error',
                    'response.tex'
                ], cwd=tmpdir, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                
                if result1.returncode != 0:
                    st.error("uplatex コンパイルエラー:")
                    st.code(f"stdout: {result1.stdout}")
                    st.code(f"stderr: {result1.stderr}")
                    return None
                
                # Step 2: dvipdfmx で .pdf ファイル生成
                result2 = subprocess.run([
                    'dvipdfmx', 
                    'response.dvi'
                ], cwd=tmpdir, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                
                if result2.returncode != 0:
                    st.error("dvipdfmx コンパイルエラー:")
                    st.code(f"stdout: {result2.stdout}")
                    st.code(f"stderr: {result2.stderr}")
                    return None
                
                pdf_path = os.path.join(tmpdir, "response.pdf")
                
                if os.path.exists(pdf_path):
                    # PDF を保存用ディレクトリにコピー
                    output_dir = "outputs"
                    os.makedirs(output_dir, exist_ok=True)
                    final_pdf_path = os.path.join(output_dir, "rigakuGPT_response.pdf")
                    shutil.copy2(pdf_path, final_pdf_path)
                    return final_pdf_path
                else:
                    st.error("PDF ファイルが生成されませんでした")
                    return None
                    
            except FileNotFoundError as e:
                st.error(f"LaTeX コンパイラが見つかりません: {str(e)}")
                st.info("uplatex と dvipdfmx がインストールされているか確認してください")
                return None
                
    except Exception as e:
        st.error(f"PDF 生成エラー: {str(e)}")
        return None

if __name__ == "__main__":
    main()
# -*- coding: utf-8 -*-
import streamlit as st
import stripe
import os
from dotenv import load_dotenv
import json
from data_manager import save_user_data, load_user_data
from utils import get_redirect_uri

# 環境変数読み込み
load_dotenv()

# Stripe設定
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

class StripePayment:
    def __init__(self):
        self.publishable_key = STRIPE_PUBLISHABLE_KEY
        self.secret_key = os.getenv("STRIPE_SECRET_KEY")
        stripe.api_key = self.secret_key
        
    def create_checkout_session(self, user_email, success_url, cancel_url):
        """Stripe Checkoutセッションを作成"""
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'jpy',
                        'product_data': {
                            'name': 'RigakuGPT Premium',
                            'description': '科学に特化した質問支援サービス - Premium プラン',
                        },
                        'recurring': {
                            'interval': 'month',
                        },
                        'unit_amount': 980,  # 980円
                    },
                    'quantity': 1,
                }],
                mode='subscription',
                customer_email=user_email,
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    'user_email': user_email,
                    'plan': 'premium'
                }
            )
            
            return session
            
        except Exception as e:
            st.error(f"Stripe Checkoutセッション作成エラー: {str(e)}")
            return None
    
    def create_portal_session(self, customer_id, return_url):
        """Stripe Customer Portalセッションを作成"""
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            
            return session
            
        except Exception as e:
            st.error(f"Customer Portalセッション作成エラー: {str(e)}")
            return None
    
    def get_customer_by_email(self, email):
        """メールアドレスから顧客情報を取得"""
        try:
            customers = stripe.Customer.list(email=email, limit=1)
            
            if customers.data:
                return customers.data[0]
            return None
            
        except Exception as e:
            st.error(f"顧客情報取得エラー: {str(e)}")
            return None
    
    def check_subscription_status(self, customer_id):
        """サブスクリプション状況を確認"""
        try:
            subscriptions = stripe.Subscription.list(
                customer=customer_id,
                status='active',
                limit=1
            )
            
            if subscriptions.data:
                return subscriptions.data[0]
            return None
            
        except Exception as e:
            st.error(f"サブスクリプション確認エラー: {str(e)}")
            return None

def show_pricing_page():
    """料金プラン表示（サイドバー対応）"""
    st.markdown("##### 💰 料金プラン") # h5にして少し小さく
    
    # Free プラン
    st.markdown("""
    <div style="border: 1px solid #ddd; border-radius: 10px; padding: 1rem; margin: 0.5rem 0;">
        <h6 style="text-align: center; color: #6c757d; margin-bottom: 0.5rem;">Free</h6>
        <p style="text-align: center; font-size: 1.2rem; font-weight: bold; margin-bottom: 1rem;">¥0</p>
        <ul style="font-size: 0.9rem; padding-left: 20px;">
            <li>OCR実行：制限あり</li>
            <li>質問回数：制限あり</li>
            <li>最新の推論モデル</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # Premium プラン
    st.markdown("""
    <div style="border: 2px solid #28a745; border-radius: 10px; padding: 1rem; margin: 0.5rem 0;">
        <h6 style="text-align: center; color: #28a745; margin-bottom: 0.5rem;">Premium</h6>
        <p style="text-align: center; font-size: 1.2rem; font-weight: bold; margin-bottom: 1rem;">¥980<small>/月</small></p>
        <p style="text-align: center; font-size: 1.2rem; font-weight: bold; margin-bottom: 1rem;">決済はStripeを用いたセキュアな方法で行われます。</p>
        <ul style="font-size: 0.9rem; padding-left: 20px;">
            <li>✅ OCR実行：より正確なモデルへの無制限のアクセス</li>
            <li>✅ 質問回数：ほぼ無制限の質問回数</li>
            <li>✅ 最高性能のモデルへのアクセス</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
        
    if st.session_state.get('authenticated', False):
        user_plan = st.session_state.user_plan
        
        if user_plan == 'free':
            if st.button("⭐ Premiumにアップグレード", type="primary", use_container_width=True):
                initiate_payment()
        else:
            st.success("✅ Premiumプラン利用中")
            if st.button("💳 支払いを管理", use_container_width=True):
                manage_subscription()
    else:
        st.info("ログインしてプランをアップグレードしてください")

def initiate_payment():
    """支払い処理を開始"""
    if not st.session_state.get('authenticated', False):
        st.error("ログインが必要です")
        return
    
    user_info = st.session_state.user_info
    user_email = user_info['email']
    user_id = user_info['sub']
    payment = StripePayment()
    
    # 成功・キャンセルURLにuser_idを追加
    base_url = "http://localhost:8501"
    success_url = f"{base_url}?payment=success&user_id={user_id}"
    cancel_url = f"{base_url}?payment=cancel&user_id={user_id}"
    
    # Checkoutセッションを作成
    session = payment.create_checkout_session(user_email, success_url, cancel_url)
    
    if session:
        # Stripe Checkoutページへリダイレクト
        st.markdown(f"""
        <div style="text-align: center; padding: 2rem;">
            <h3>支払い手続きを開始します</h3>
            <p>下のボタンをクリックして支払いページに移動してください</p>
            <a href="{session.url}" target="_blank">
                <button style="background-color: #635bff; color: white; padding: 12px 24px; border: none; border-radius: 5px; font-size: 16px; cursor: pointer;">
                    💳 支払いページへ
                </button>
            </a>
        </div>
        """, unsafe_allow_html=True)

def manage_subscription():
    """サブスクリプション管理"""
    if not st.session_state.get('authenticated', False):
        st.error("ログインが必要です")
        return
    
    user_email = st.session_state.user_info['email']
    payment = StripePayment()
    
    # 顧客情報を取得
    customer = payment.get_customer_by_email(user_email)
    
    if customer:
        # Customer Portalセッションを作成
        return_url = get_redirect_uri()
        portal_session = payment.create_portal_session(customer.id, return_url)
        
        if portal_session:
            st.markdown(f"""
            <div style="text-align: center; padding: 2rem;">
                <h3>支払い設定管理</h3>
                <p>下のボタンをクリックして支払い設定を管理してください</p>
                <a href="{portal_session.url}" target="_blank">
                    <button style="background-color: #635bff; color: white; padding: 12px 24px; border: none; border-radius: 5px; font-size: 16px; cursor: pointer;">
                        💳 支払い設定を管理
                    </button>
                </a>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.error("顧客情報が見つかりません")

def handle_payment_callback():
    """支払い完了コールバック処理"""
    query_params = st.query_params
    
    # 支払い後のリダイレクトか確認
    if 'payment' in query_params and 'user_id' in query_params:
        user_id = query_params.get('user_id')
        user_data = load_user_data(user_id)

        # ユーザーデータが存在する場合、セッションを復元
        if user_data and 'user_info' in user_data:
            st.session_state.authenticated = True
            st.session_state.user_info = user_data['user_info']
            st.session_state.user_plan = user_data.get('plan', 'free')
            st.session_state.ocr_usage_count = user_data.get('ocr_usage_count', 0)
            st.session_state.question_usage_count = user_data.get('question_usage_count', 0)
        else:
            # ユーザーデータがない場合は処理を中断
            return

        payment_status = query_params.get('payment')
        
        if payment_status == 'success':
            st.success("✅ 支払いが完了しました！Premiumプランが有効化されました。")
            
            # ユーザープランを更新
            st.session_state.user_plan = 'premium'
            st.session_state.ocr_usage_count = 0
            st.session_state.question_usage_count = 0
            
            # ユーザーデータを更新して保存
            user_data['plan'] = 'premium'
            user_data['ocr_usage_count'] = 0
            user_data['question_usage_count'] = 0
            save_user_data(user_id, user_data)

        elif payment_status == 'cancel':
            st.info("支払いがキャンセルされました")

        # 処理が終わったらクエリパラメータをクリアしてリロード
        st.query_params.clear()
        st.rerun()

def verify_premium_access(user_email):
    """Premiumアクセス権限を確認"""
    payment = StripePayment()
    
    # 顧客情報を取得
    customer = payment.get_customer_by_email(user_email)
    
    if customer:
        # アクティブなサブスクリプションを確認
        subscription = payment.check_subscription_status(customer.id)
        
        if subscription:
            return True
    
    return False

def init_payment_session():
    """支払い関連のセッション状態を初期化"""
    if 'subscription_status' not in st.session_state:
        st.session_state.subscription_status = None

def show_payment_info():
    """支払い情報表示（管理者用）"""
    if st.session_state.get('authenticated', False):
        user_email = st.session_state.user_info['email']
        
        # 管理者のみ表示
        if user_email in ["admin@example.com"]:  # 管理者のメールアドレス
            with st.expander("💳 支払い情報（管理者）"):
                payment = StripePayment()
                customer = payment.get_customer_by_email(user_email)
                
                if customer:
                    st.json({
                        "customer_id": customer.id,
                        "email": customer.email,
                        "created": customer.created
                    })
                    
                    subscription = payment.check_subscription_status(customer.id)
                    if subscription:
                        st.json({
                            "subscription_id": subscription.id,
                            "status": subscription.status,
                            "current_period_end": subscription.current_period_end
                        })
                else:
                    st.write("顧客情報なし")
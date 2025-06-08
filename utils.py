# -*- coding: utf-8 -*-
import streamlit as st

def get_redirect_uri():
    """実行環境に応じてリダイレクトURIを動的に取得"""
    try:
        # Streamlitの内部APIを安全にインポート
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        ctx = get_script_run_ctx()
        
        if ctx:
            # st.query_paramsからホスト名を取得
            server_address = st.query_params.get('_st_host')
            if server_address:
                return f"https://{server_address}"
                
    except (ImportError, AttributeError):
        # Streamlit Cloud以外の環境（ローカルなど）の場合
        pass
        
    # デフォルトはローカルホスト
    return "http://localhost:8501" 
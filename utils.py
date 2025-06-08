# -*- coding: utf-8 -*-
import streamlit as st
import os

def get_redirect_uri():
    """環境変数からリダイレクトURIを取得"""
    base_url = os.getenv("BASE_URL")
    
    # 環境変数が設定されていればそれを使い、なければローカル開発用にフォールバック
    return base_url if base_url else "http://localhost:8501" 
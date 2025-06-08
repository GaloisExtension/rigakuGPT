# -*- coding: utf-8 -*-
import os
import json
import streamlit as st

# データ保存ディレクトリ
USER_DATA_DIR = "user_data"
os.makedirs(USER_DATA_DIR, exist_ok=True)

def save_user_data(user_id, data):
    """ユーザーデータをJSONファイルに保存"""
    try:
        filepath = os.path.join(USER_DATA_DIR, f"{user_id}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.warning(f"ユーザーデータの保存に失敗しました: {e}")

def load_user_data(user_id):
    """JSONファイルからユーザーデータを読み込み"""
    if not user_id:
        return {}
    try:
        filepath = os.path.join(USER_DATA_DIR, f"{user_id}.json")
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        st.warning(f"ユーザーデータの読み込みに失敗しました: {e}")
    return {} # ファイルがない、またはエラーの場合は空の辞書を返す 
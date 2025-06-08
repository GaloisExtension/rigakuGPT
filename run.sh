#!/bin/bash
# 数学質問支援サービス起動スクリプト

echo "数学質問支援サービスを起動中..."
source mathgpt_env/bin/activate
streamlit run app.py
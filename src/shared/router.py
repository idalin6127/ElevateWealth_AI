import streamlit as st

def goto(page_path: str):
    try:
        st.switch_page(page_path)
    except Exception:
        # 兼容旧版方案可在此添加 URL 参数兜底
        raise
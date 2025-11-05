# pages/01_Startup_Companion.py（位于体检表项目根目录的 /pages 下）
import sys, pathlib, streamlit as st

st.set_page_config(page_title="ElevateWealth AI · Startup Companion", layout="wide")

ROOT = pathlib.Path(__file__).resolve().parents[1]  # 指向含 app.py 的根
MINBIZ_UI = ROOT / "minbiz_agent" / "src" / "ui"
SRC = ROOT / "src"

# 确保 Python 找到创业体 UI
for p in (MINBIZ_UI, ROOT):
    if str(p) not in sys.path:
        sys.path.append(str(p))

from app_minbiz_chat import render_minbiz_ui
# from shared.router import goto   # 如果本页也要跳转，可引入
# from shared.context import *     # 如需读取上下文，可引入

render_minbiz_ui()

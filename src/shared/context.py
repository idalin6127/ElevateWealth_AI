import streamlit as st
KEY_DECISION_TRACK = "decision_track"
KEY_FIN_SUMMARY = "financial_summary"

def set_decision_track(v): st.session_state[KEY_DECISION_TRACK] = v
def get_decision_track(default="职业路径"): return st.session_state.get(KEY_DECISION_TRACK, default)
def set_financial_summary(v: dict): st.session_state[KEY_FIN_SUMMARY] = v
def get_financial_summary(): return st.session_state.get(KEY_FIN_SUMMARY, {})
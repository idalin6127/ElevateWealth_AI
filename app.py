# app.py (public/demo version)
# -*- coding: utf-8 -*-
"""
ElevateWealth AI - Demo App
公开版：展示整体架构与交互流程，隐藏内部完整财务引擎与私密数据。
- 模块：
  1) 家庭财务体检（简化版指标与建议）
  2) 创业智能体 MinBiz Agent（调用 minbiz_agent 模块）
  3) 投资理财（预留入口）
  4) 职业晋升（预留入口）
注：本版本所有计算与建议均为示意用途，不构成专业/个性化财务建议。
"""

from __future__ import annotations

import os
from typing import Dict, Any

import streamlit as st
import pandas as pd

import pathlib
import sys


# ========= 基本工具 & 多语言 =========

def get_lang() -> str:
    """简单语言选择：zh / en"""
    return st.session_state.get("lang", "zh")


def L(zh: str, en: str) -> str:
    """中英文切换"""
    return zh if get_lang() == "zh" else en


def amount(v: float, currency: str = "¥") -> str:
    try:
        return f"{currency}{v:,.0f}"
    except Exception:
        return f"{currency}{v}"


def ratio_fmt(v: float) -> str:
    try:
        return f"{v*100:.1f}%"
    except Exception:
        return "-"


def level_by_threshold(
    value: float,
    is_good,
    is_ok,
) -> str:
    """
    根据阈值给出 good / ok / bad。

    is_good/is_ok: callable, 接受 value, 返回 bool
    """
    try:
        if is_good(value):
            return "good"
        if is_ok(value):
            return "ok"
        return "bad"
    except Exception:
        return "bad"


def color_tag(level: str) -> str:
    if level == "good":
        return "🟢 " + L("良好", "Good")
    if level == "ok":
        return "🟡 " + L("可改善", "Okay")
    return "🔴 " + L("需关注", "Needs attention")


def get_currency() -> str:
    return st.session_state.get("currency", "¥")


# ========= 简化版财务体检引擎（公开版） =========

def run_checkup(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    精简版家庭财务体检：
    - 只计算若干关键指标，用于开源示例演示
    - 不包含完整的 FIRE 引擎 / 复杂资产重构逻辑
    """
    g = lambda k: float(data.get(k, 0) or 0.0)

    # 收入与支出
    monthly_income = g("monthly_income")
    monthly_side = g("monthly_side")
    passive_income = g("passive_income")
    fixed_spend = g("fixed_spend")
    flex_spend = g("flex_spend")
    debt_spend = g("debt_spend")

    # 应急金（现金储备）
    emergency_fund = g("emergency_fund")

    # 资产（粗粒度）
    a_home = g("asset_home")
    a_rental = g("asset_rental")
    a_stock_div = g("asset_stock_div")
    a_stock_growth = g("asset_stock_growth")
    a_bond_fund = g("asset_bond_fund")
    a_cash = g("asset_cash")
    a_other = g("asset_other")

    # 负债
    d_mortgage = g("debt_mortgage")
    d_car = g("debt_car")
    d_cc = g("debt_cc")
    d_other = g("debt_other")

    total_income = monthly_income + monthly_side + passive_income
    total_spend = fixed_spend + flex_spend + debt_spend
    net_cf = total_income - total_spend

    annual_spend = total_spend * 12
    annual_passive = passive_income * 12

    total_assets = a_home + a_rental + a_stock_div + a_stock_growth + a_bond_fund + a_cash + a_other
    total_debt = d_mortgage + d_car + d_cc + d_other

    earning_assets = a_stock_div + a_rental + a_bond_fund
    growth_assets = a_stock_growth
    draining_assets = a_home
    neutral_assets = a_cash + a_other

    # 指标
    if annual_spend > 0:
        ef_months = emergency_fund / (annual_spend / 12)
        passive_cover = annual_passive / annual_spend
    else:
        ef_months = 0
        passive_cover = 0

    if total_assets > 0:
        earning_ratio = earning_assets / total_assets
        debt_ratio = total_debt / total_assets
    else:
        earning_ratio = 0
        debt_ratio = 0

    ef_level = level_by_threshold(ef_months, lambda v: v >= 6, lambda v: 3 <= v < 6)
    earn_level = level_by_threshold(earning_ratio, lambda v: v >= 0.5, lambda v: 0.3 <= v < 0.5)
    debt_level = level_by_threshold(debt_ratio, lambda v: v < 0.5, lambda v: 0.5 <= v < 0.7)
    cov_level = level_by_threshold(passive_cover, lambda v: v >= 1.0, lambda v: 0.5 <= v < 1.0)
    cf_level = "good" if net_cf >= 0 else "bad"

    issues = []
    if net_cf < 0:
        issues.append(L("月净现金流为负，存在入不敷出风险。", "Monthly net cashflow is negative; risk of overspending."))
    elif net_cf < 500:
        issues.append(L("月净现金流偏低，积累资产速度可能较慢。", "Monthly net cashflow is low; asset building may be slow."))

    if ef_level == "bad":
        issues.append(L("应急金不足 3 个月支出，抗风险能力偏弱。", "Emergency fund < 3 months of spend; buffer is weak."))
    if debt_level != "good":
        issues.append(L("资产负债率偏高，建议逐步降低杠杆。", "Debt-to-asset ratio is elevated; consider deleveraging."))
    if earn_level != "good":
        issues.append(L("生钱资产占比不高，被动收入基础较薄。", "Earning-asset share is modest; passive income base is thin."))
    if cov_level != "good":
        issues.append(L("被动收入尚未覆盖生活支出，仍在通往财务自由的路上。", "Passive income does not yet cover living expenses."))

    actions = [
        L("确保每月有正向结余，并优先给“自己账户”存钱。", "Ensure positive monthly surplus and pay yourself first."),
        L("逐步将应急金提升到 3–6 个月支出水平。", "Build 3–6 months of expenses as emergency fund."),
        L("增加股息/租金/利息类生钱资产，减少纯消费性负债。", "Increase cash-generating assets and reduce pure consumption debt."),
    ]
    # 去重
    actions = list(dict.fromkeys(actions))

    report = {
        "summary": {
            "月净现金流": net_cf,
            "应急金覆盖(月)": ef_months,
            "生钱资产占比": earning_ratio,
            "资产负债率": debt_ratio,
            "被动收入覆盖率": passive_cover,
        },
        "levels": {
            "现金流": cf_level,
            "应急金": ef_level,
            "生钱占比": earn_level,
            "负债率": debt_level,
            "被动覆盖": cov_level,
        },
        "breakdown": {
            "收入(税后+副业+被动)": total_income,
            "支出(固定+弹性+负债)": total_spend,
            "年被动收入": annual_passive,
            "年总支出": annual_spend,
            "总资产": total_assets,
            "总负债": total_debt,
            "生钱资产估算": earning_assets,
            "成长型资产估算": growth_assets,
            "中性资产估算": neutral_assets,
            "耗钱资产估算": draining_assets,
        },
        "issues": issues,
        "actions": actions,
    }

    # 给“创业智能体”等后续模块用的高层摘要（不暴露细节）
    risk_txt = str(data.get("risk_level") or "")
    if get_lang() == "zh":
        risk_for_agent = {
            "稳健": "偏保守",
            "平衡": "中等",
            "进取": "偏激进",
            "Low": "偏保守",
            "Medium": "中等",
            "High": "偏激进",
        }.get(risk_txt, "中等")
    else:
        risk_for_agent = {
            "Conservative": "conservative",
            "Balanced": "balanced",
            "Aggressive": "aggressive",
        }.get(risk_txt, "balanced")

    agent_summary = {
        "cashflow_monthly": net_cf,
        "runway_months": ef_months,
        "risk_level": risk_for_agent,
        "goal_years": float(data.get("fi_years_target") or 5),
    }

    return {
        "report": report,
        "agent_summary": agent_summary,
    }


# ========= Streamlit 页面：主入口 =========

def render_wealth_checkup():
    st.header(L("💰 家庭财务健康体检（示例版）", "💰 Family Financial Checkup (Demo)"))
    st.caption(
        L(
            "本页面为简化示意版，仅展示数据收集与指标计算流程，不构成任何投资建议。",
            "This is a simplified demo view only. It does not constitute financial advice."
        )
    )

    with st.form("checkup_form"):
        st.subheader(L("1. 收入与支出", "1. Income & Expenses"))
        c1, c2, c3 = st.columns(3)
        with c1:
            monthly_income = st.number_input(L("税后月收入", "Net monthly income"), min_value=0.0, step=100.0)
            monthly_side = st.number_input(L("副业/额外收入", "Side income"), min_value=0.0, step=100.0)
        with c2:
            passive_income = st.number_input(L("被动收入（月）", "Passive income (monthly)"), min_value=0.0, step=100.0)
            fixed_spend = st.number_input(L("固定支出（月房租/房贷等）", "Fixed spend per month"), min_value=0.0, step=100.0)
        with c3:
            flex_spend = st.number_input(L("弹性支出（月生活消费）", "Flexible spend per month"), min_value=0.0, step=100.0)
            debt_spend = st.number_input(L("债务支出（月还款总额）", "Debt payment per month"), min_value=0.0, step=100.0)

        st.subheader(L("2. 应急金与资产负债", "2. Emergency Fund & Balance Sheet"))
        emergency_fund = st.number_input(L("应急金余额（现金/稳健资产）", "Emergency fund balance"), min_value=0.0, step=500.0)

        st.markdown(L("**主要资产（粗略估算即可）：**", "**Main assets (rough estimates):**"))
        a1, a2, a3 = st.columns(3)
        with a1:
            asset_home = st.number_input(L("自住房产净值", "Home equity"), min_value=0.0, step=10000.0)
            asset_rental = st.number_input(L("投资房产净值", "Rental property equity"), min_value=0.0, step=10000.0)
        with a2:
            asset_stock_div = st.number_input(L("股票/基金（偏股息）", "Dividend/income assets"), min_value=0.0, step=5000.0)
            asset_stock_growth = st.number_input(L("股票/基金（偏成长）", "Growth assets"), min_value=0.0, step=5000.0)
        with a3:
            asset_bond_fund = st.number_input(L("债券/货基/理财", "Bond/cash-like assets"), min_value=0.0, step=5000.0)
            asset_cash = st.number_input(L("现金/活期/其他", "Cash & others"), min_value=0.0, step=5000.0)

        asset_other = st.number_input(L("其他资产（如公司股权等）", "Other assets (e.g., equity)"), min_value=0.0, step=5000.0)

        st.markdown(L("**主要负债（粗略估算）：**", "**Main liabilities (rough estimates):**"))
        d1, d2, d3 = st.columns(3)
        with d1:
            debt_mortgage = st.number_input(L("房贷余额", "Mortgage balance"), min_value=0.0, step=10000.0)
        with d2:
            debt_car = st.number_input(L("车贷余额", "Car loan balance"), min_value=0.0, step=5000.0)
        with d3:
            debt_cc = st.number_input(L("信用卡/消费贷", "Credit/consumer debt"), min_value=0.0, step=5000.0)
        debt_other = st.number_input(L("其他负债", "Other debts"), min_value=0.0, step=5000.0)

        st.subheader(L("3. 风险偏好与目标", "3. Risk profile & goals"))
        risk_level = st.selectbox(
            L("你的风险偏好？", "Your risk profile?"),
            L(["稳健", "平衡", "进取"], ["Conservative", "Balanced", "Aggressive"]),
        )
        fi_years_target = st.number_input(
            L("期望在多少年内显著接近/实现财务自由？", "In how many years would you like to be close to FIRE?"),
            min_value=1.0,
            max_value=40.0,
            value=10.0,
            step=1.0,
        )

        submitted = st.form_submit_button(L("生成体检结果（示意）", "Generate demo report"))
        if submitted:
            st.session_state["checkup_data"] = {
                "monthly_income": monthly_income,
                "monthly_side": monthly_side,
                "passive_income": passive_income,
                "fixed_spend": fixed_spend,
                "flex_spend": flex_spend,
                "debt_spend": debt_spend,
                "emergency_fund": emergency_fund,
                "asset_home": asset_home,
                "asset_rental": asset_rental,
                "asset_stock_div": asset_stock_div,
                "asset_stock_growth": asset_stock_growth,
                "asset_bond_fund": asset_bond_fund,
                "asset_cash": asset_cash,
                "asset_other": asset_other,
                "debt_mortgage": debt_mortgage,
                "debt_car": debt_car,
                "debt_cc": debt_cc,
                "debt_other": debt_other,
                "risk_level": risk_level,
                "fi_years_target": fi_years_target,
            }

    data = st.session_state.get("checkup_data")
    if not data:
        st.info(L("填写表单并提交后，这里会显示示例体检结果。", "Fill the form and submit to see a demo report here."))
        return

    CURR = get_currency()
    result = run_checkup(data)
    report = result["report"]
    agent_summary = result["agent_summary"]
    st.session_state["financial_summary"] = agent_summary  # 给创业智能体用（如需）

    st.divider()
    st.subheader(L("📊 核心指标概览", "📊 Key indicators"))

    summary = report["summary"]
    levels = report["levels"]

    c1, c2, c3 = st.columns(3)
    with c1:
        lvl = levels["现金流"]
        st.metric(
            L("月净现金流", "Monthly net cashflow"),
            amount(summary["月净现金流"], CURR),
            help=color_tag(lvl),
        )
    with c2:
        lvl = levels["应急金"]
        st.metric(
            L("应急金覆盖（月）", "Emergency fund (months)"),
            f"{summary['应急金覆盖(月)']:.1f}",
            help=color_tag(lvl),
        )
    with c3:
        lvl = levels["负债率"]
        st.metric(
            L("资产负债率", "Debt-to-asset ratio"),
            ratio_fmt(summary["资产负债率"]),
            help=color_tag(lvl),
        )

    st.subheader(L("🔍 关键观察", "🔍 Key observations"))
    if report["issues"]:
        for it in report["issues"]:
            st.markdown(f"- {it}")
    else:
        st.markdown(L("整体状况良好，可在安全边际内提高投资效率。", "Overall picture looks healthy; you can focus on efficient investing with proper safety margins."))

    st.subheader(L("📌 优先行动建议", "📌 Suggested next steps"))
    for act in report["actions"]:
        st.markdown(f"- {act}")

    st.subheader(L("📁 计算快照", "📁 Calculation snapshot"))
    bd = report["breakdown"]
    df = pd.DataFrame.from_dict(bd, orient="index", columns=[L("金额/数值", "Amount / value")])
    st.dataframe(df)


def render_minbiz_agent():
    st.header(L("🚀 创业智能体 MinBiz Agent", "🚀 Startup Companion - MinBiz Agent"))
    st.caption(
        L(
            "这是一个基于 RAG + LLM 的创业陪伴智能体，用于探索方向、品牌策略与执行建议。",
            "This is a RAG + LLM based startup companion agent for direction, branding and execution support."
        )
    )

    ROOT = pathlib.Path(__file__).resolve().parent
    MINBIZ_UI = ROOT / "minbiz_agent" / "src" / "ui"
    sys.path.append(str(MINBIZ_UI))

    try:
        from app_minbiz_chat import render_minbiz_ui  # type: ignore
        render_minbiz_ui()
    except Exception as e:
        st.error(L("无法加载创业智能体界面，请检查 minbiz_agent 模块。", "Failed to load MinBiz UI. Please check minbiz_agent module."))
        st.exception(e)


def render_invest_agent_placeholder():
    st.header(L("📈 投资理财智能体（规划中）", "📈 Investment Agent (Coming Soon)"))
    st.info(
        L(
            "这里未来将接入：ETF 研究、资产配置建议、回撤与风险分析等功能。",
            "This section will host ETF research, asset allocation suggestions, and risk analytics in future versions."
        )
    )


def render_career_agent_placeholder():
    st.header(L("🎓 职业晋升智能体（规划中）", "🎓 Career Growth Agent (Planned)"))
    st.info(
        L(
            "这里未来将提供：职业路径设计、能力模型拆解、沟通力与影响力提升建议等。",
            "This section will host career path design, skills breakdown, and communication/leadership coaching in future releases."
        )
    )


# ========= 主入口 =========

def main():
    st.set_page_config(
        page_title="ElevateWealth AI",
        page_icon="💡",
        layout="wide",
    )

    # 顶部栏：语言 & 货币
    c1, c2, c3 = st.columns([0.4, 0.3, 0.3])
    with c1:
        st.markdown("### ElevateWealth AI")
        st.caption(L("智能财富成长平台（公开示例版）", "Intelligent Wealth Growth Platform (public demo)"))
    with c2:
        lang = st.selectbox("Language / 语言", ["zh", "en"], index=0 if get_lang() == "zh" else 1, key="lang")
        st.session_state["lang"] = lang
    with c3:
        currency = st.selectbox(L("货币符号", "Currency symbol"), ["¥", "$", "€"], key="currency")
        st.session_state["currency"] = currency

    st.sidebar.title("🧭 " + L("功能导航", "Navigation"))
    module = st.sidebar.radio(
        L("请选择模块", "Select a module"),
        [
            L("💰 财富体检", "💰 Wealth Checkup"),
            L("🚀 创业智能体", "🚀 Startup Agent"),
            L("📈 投资智能体（预留）", "📈 Investment Agent (placeholder)"),
            L("🎓 职业晋升智能体（预留）", "🎓 Career Agent (placeholder)"),
        ],
    )

    if "财富体检" in module or "Wealth Checkup" in module:
        render_wealth_checkup()
    elif "创业" in module or "Startup" in module:
        render_minbiz_agent()
    elif "投资" in module or "Investment" in module:
        render_invest_agent_placeholder()
    elif "职业" in module or "Career" in module:
        render_career_agent_placeholder()


if __name__ == "__main__":
    main()

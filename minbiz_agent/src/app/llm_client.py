# src/app/llm_client.py
# -*- coding: utf-8 -*-
from __future__ import annotations  # ← 必须放在文件最前（文档字符串后第一条语句）

"""
统一的大模型调用封装：
- chat_json：强制输出 JSON（用于 Draft/Refine）
- chat_text：普通文本（用于最终合成）
环境变量：
  OPENAI_API_KEY            必填
  OPENAI_BASE_URL           选填（自定义网关/代理用）
  OPENAI_ORG                选填
  MINBIZ_OPENAI_MODEL       选填（不传 model 参数时的默认）
"""

import os, json, time
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
load_dotenv()  # 自动读取项目根目录 .env

# 也可以改成别家 SDK；这里以 openai >= 1.0 为例
def _openai_client():
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 OPENAI_API_KEY 环境变量")
    base_url = os.environ.get("OPENAI_BASE_URL")  # 可选
    org = os.environ.get("OPENAI_ORG")            # 可选
    return OpenAI(api_key=api_key, base_url=base_url, organization=org)

def _retry(func, *args, **kwargs):
    tries = kwargs.pop("_tries", 3)
    delay = kwargs.pop("_delay", 1.0)
    for i in range(tries):
        try:
            return func(*args, **kwargs)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2.0, 8.0)

def chat_json(messages: List[Dict[str, str]], model: Optional[str] = None, temperature: float = 0.2) -> Dict[str, Any]:
    """
    让模型以 JSON 对象形式返回（不含 markdown 代码块）。
    """
    client = _openai_client()
    model = model or os.environ.get("MINBIZ_OPENAI_MODEL", "gpt-4o-mini")

    def _call():
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return resp

    resp = _retry(_call)
    content = resp.choices[0].message.content
    try:
        return json.loads(content)
    except Exception as e:
        raise ValueError(f"期望 JSON 输出，但解析失败：{e}\n原始输出：{content!r}")

def chat_text(messages: List[Dict[str, str]], model: Optional[str] = None, temperature: float = 0.3) -> str:
    """
    普通文本回答。
    """
    client = _openai_client()
    model = model or os.environ.get("MINBIZ_OPENAI_MODEL", "gpt-4o")

    def _call():
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )
        return resp

    resp = _retry(_call)
    return resp.choices[0].message.content.strip()

# src/app/validators.py
from src.app.schemas import Draft, Refined
from typing import Set

def check_support_ids_exist(draft: Draft, valid_ids: Set[str]):
    for c in draft.claims:
        for sid in c.support:
            if sid not in valid_ids:
                raise ValueError(f"support 引用不存在: {sid}")

def quote_budget_ok(total_quote_chars: int, max_budget: int = 300):
    if total_quote_chars > max_budget:
        raise ValueError(f"直接引用超额: {total_quote_chars}>{max_budget}")

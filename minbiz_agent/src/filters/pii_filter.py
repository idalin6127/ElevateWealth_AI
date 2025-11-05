import re
from typing import Dict, Iterable

DEFAULT_PATTERNS = {
    "email": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    "phone": r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{4}",
    "name_henry": r"\b(Henry|亨利|澳洲\s*Henry)\b",
}

def redact(text: str, policy: Dict[str, str] = None) -> str:
    if not text:
        return text
    rules = {k:v for k,v in (policy or {}).items()}
    rules.setdefault("name_henry", "[REDACTED-NAME]")
    rules.setdefault("email", "[REDACTED-EMAIL]")
    rules.setdefault("phone", "[REDACTED-PHONE]")
    out = text
    for key, repl in rules.items():
        pat = DEFAULT_PATTERNS.get(key, key)
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out

def redact_stream(lines: Iterable[str], policy: Dict[str, str] = None):
    for line in lines:
        yield redact(line, policy=policy)

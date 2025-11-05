import re
MAX_VERBATIM = 100
def enforce_ip(output_text: str) -> str:
    output_text = re.sub(r"\b(Henry|亨利|澳洲\s*Henry)\b", "[REDACTED-NAME]", output_text, flags=re.IGNORECASE)
    output_text = re.sub(r"“([^”]{101,})”", "“[EXCERPT-TRIMMED]”", output_text)
    output_text = re.sub(r"\"([^\"]{101,})\"", "\"[EXCERPT-TRIMMED]\"", output_text)
    return output_text

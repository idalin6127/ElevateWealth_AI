# src/app/schemas.py
# -*- coding: utf-8 -*-
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class EvidenceHit(BaseModel):
    chunk_id: str
    title: Optional[str] = ""
    start_s: float
    end_s: float
    snippet: str = ""
    source: str
    type: Literal["internal"] = "internal"

class EvidencePack(BaseModel):
    question: str
    # 不用 conlist；保持兼容 pydantic v1/v2
    hits: List[EvidenceHit] = Field(default_factory=list)

class Claim(BaseModel):
    id: str
    text: str
    # 支持列表，长度校验交给上游 Step6
    support: List[str] = Field(default_factory=list)

class Draft(BaseModel):
    claims: List[Claim] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    tone: Literal["professional", "casual", "formal"] = "professional"

class BGAddition(BaseModel):
    text: str
    source: Literal["external:web", "external:api", "external:paper", "external:other"]
    citation: str

class Conflict(BaseModel):
    claim_id: str
    external: str
    internal: str
    resolution: str

class Refined(BaseModel):
    claims: List[Claim] = Field(default_factory=list)
    bg_additions: List[BGAddition] = Field(default_factory=list)
    conflicts: List[Conflict] = Field(default_factory=list)

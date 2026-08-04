from typing import List, Literal, Optional
from pydantic import BaseModel


# ── Request ───────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    video_url: str
    provider: Literal["server", "gemini"] = "server"
    # Required when provider="gemini"; ignored for provider="server".
    # Treated as a secret: never logged, stored, or echoed back in any response.
    api_key: Optional[str] = None


# ── Response ──────────────────────────────────────────────────────────────────

class ScoreBreakdown(BaseModel):
    educational_value: int
    community_trust: int
    clarity: int
    beginner_friendliness: int


class AnalyzeResponse(BaseModel):
    watch_score: int
    score_breakdown: ScoreBreakdown
    outdated_risk: Literal["low", "medium", "high"]
    outdated_confidence: int
    outdated_evidence: List[str]
    misinformation_risk: Literal["low", "medium", "high"]
    misinformation_evidence: List[str]
    community_evidence: List[str]
    summary: str
    recommendation: Literal[
        "Highly Recommended", "Recommended", "Watch with Caution", "Not Recommended"
    ]
    pros: List[str]
    cons: List[str]

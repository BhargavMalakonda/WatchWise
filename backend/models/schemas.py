from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ── Request ───────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    video_url: str

    provider: Literal["server", "gemini"] = "server"

    # Required when provider="gemini"; ignored when provider="server".
    # Treated as a secret: never logged, stored, or echoed back.
    api_key: Optional[str] = None


# ── Response Models ───────────────────────────────────────────────────────────

class ScoreBreakdown(BaseModel):
    educational_value: int = Field(ge=0, le=100)
    community_reception: int = Field(ge=0, le=100)
    clarity: int = Field(ge=0, le=100)
    beginner_friendliness: int = Field(ge=0, le=100)


class InclusionSignals(BaseModel):
    accessible_for_beginners: Literal["low", "medium", "high"]
    jargon_level: Literal["low", "medium", "high"]
    learning_barrier: Literal["low", "medium", "high"]


class Claim(BaseModel):
    claim: str

    claim_type: Literal[
        "fact",
        "statistic",
        "opinion",
        "prediction",
        "comparison",
        "recommendation",
        "trend",
    ]

    importance: Literal[
        "high",
        "medium",
        "low",
    ]

    verification_status: Literal[
        "supported",
        "needs_context",
        "needs_verification",
        "insufficient_information",
    ]

    confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence in the assigned verification status."
    )

    why_question: List[str]

    mil_skill: Literal[
        "Source Evaluation",
        "Evidence Verification",
        "Context Awareness",
        "Recognizing Bias",
        "Checking Recency",
        "Opinion vs Fact",
    ]


class CommunityPerspective(BaseModel):
    agreement: Literal["high", "medium", "low"]
    disagreement: Literal["high", "medium", "low"]
    notes: List[str]


class InformationSignals(BaseModel):
    evidence_quality: Literal["low", "medium", "high"]
    context_completeness: Literal["low", "medium", "high"]
    recency: Literal["low", "medium", "high"]


class MILLearning(BaseModel):
    skill: str
    lesson: str
    why_it_matters: str
    question_to_ask: str


class BeforeYouShareItem(BaseModel):
    question: str
    status: Literal["pass", "warning", "fail"]


class OverallAssessment(BaseModel):
    label: str

    confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence in the assessment."
    )


class LearningOutcome(BaseModel):
    takeaway: str


class AnalyzeResponse(BaseModel):

    overall_assessment: OverallAssessment

    score_breakdown: ScoreBreakdown

    claims: List[Claim]

    community_perspective: CommunityPerspective

    information_signals: InformationSignals

    inclusion_signals: InclusionSignals

    mil_learning: List[MILLearning] = Field(
        min_length=1,
        max_length=3,
    )

    learning_outcomes: List[LearningOutcome] = Field(
        min_length=1,
        max_length=3,
    )

    critical_thinking_prompts: List[str]

    before_you_share: List[BeforeYouShareItem] = Field(
        min_length=3,
        max_length=3,
    )

    outdated_risk: Literal["low", "medium", "high"]

    outdated_confidence: int = Field(
        ge=0,
        le=100,
    )

    outdated_evidence: List[str]

    misinformation_risk: Literal["low", "medium", "high"]

    misinformation_evidence: List[str]

    community_evidence: List[str]

    summary: str

    recommendation: Literal[
        "Highly Recommended",
        "Recommended",
        "Watch with Caution",
        "Not Recommended",
    ]

    pros: List[str]

    cons: List[str]
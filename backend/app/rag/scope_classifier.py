"""
backend/app/rag/scope_classifier.py
===================================
Comprehensive scope classification module for the Eureka RAG Chatbot.
Follows Problem Statement §§9-11 and Task Requirements §3-4:
- Distinguishes IN_SCOPE, OUT_OF_SCOPE, and AMBIGUOUS.
- Avoids treating off-topic questions as missing-information queries.
- Generates friendly, natural redirects tailored to off-topic domains (food, sports, weather, trivia).
- Mentions only verified knowledge-base categories (software development, cloud integration, AI consulting, case studies).
- Maintains backward-compatibility with existing classify_scope() signature and tests.
"""
from __future__ import annotations

import enum
import re
from typing import Optional


class ScopeCategory(str, enum.Enum):
    IN_SCOPE = "in_scope"
    OUT_OF_SCOPE = "out_of_scope"
    AMBIGUOUS = "ambiguous"


# Alias for compatibility with external references
QueryScope = ScopeCategory


# Standard fallback specified in Problem Statement §11.1
OUT_OF_SCOPE_FALLBACK_TEXT = (
    "I am the Ask Eureka AI assistant, designed specifically to help with information "
    "about Eureka Solutions, our enterprise services, technology solutions, industries, "
    "and client case studies. I cannot assist with queries outside this scope. "
    "Please feel free to ask about our software engineering, AI automation, or industry solutions."
)



# Specific off-topic domains with targeted pattern detection and conversational redirects
_FOOD_PATTERN = re.compile(
    r"\b(rajma\s+chawal|biryani|pizza|burger|samosa|dal\s+makhani|roti|paneer|pasta|"
    r"recipe\s+for|how\s+to\s+cook|bake\s+(a|an)?|baking\b|ingredients\s+for|order\s+food|"
    r"food\s+delivery|menu\s+card|restaurant|lunch\s+menu|dinner\s+menu|breakfast|snack)\b",
    re.I,
)

_SPORTS_PATTERN = re.compile(
    r"\b(cricket|football|soccer|baseball|basketball|tennis|rugby|chess|badminton|"
    r"match\s+yesterday|who\s+won\s+(the\s+)?(match|game|tournament|cup|trophy|ipl|world\s+cup|super\s+bowl)|"
    r"score\s+of|live\s+score|ipl\b|fifa\b|olympics?)\b",
    re.I,
)

_WEATHER_PATTERN = re.compile(
    r"\b(weather\s+in|weather\s+forecast|forecast\s+for|temperature\s+today|temperature\s+in|rain\s+today|rain\s+tomorrow)\b",
    re.I,
)

_TRIVIA_POLITICS_PATTERN = re.compile(
    r"\b(capital\s+(city\s+)?of|president\s+of|prime\s+minister\s+of|population\s+of|who\s+discovered|"
    r"when\s+did\s+world\s+war|presidential\s+election|who\s+is\s+the\s+richest\s+person|history\s+of\s+ancient)\b",
    re.I,
)

_ENTERTAINMENT_PATTERN = re.compile(
    r"\b(best\s+movie|actor\s+in|actress\s+in|who\s+acted\s+in|celebrity\s+gossip|pop\s+song|album\s+release|hollywood|bollywood)\b",
    re.I,
)

_MATH_CODING_EXERCISE_PATTERN = re.compile(
    r"\b(solve\s+this\s+math|calculate\s+the\s+derivative|calculate\s+the\s+integral|"
    r"write\s+code\s+in\s+(c\+\+|python|java|rust|go)\s+to\s+implement\s+(a\s+)?(red-black\s+tree|binary\s+search\s+tree|linked\s+list)|"
    r"solve\s+(x\^2|the\s+equation))\b",
    re.I,
)

_CREATIVE_WRITING_PATTERN = re.compile(
    r"\b(write\s+a\s+poem|write\s+a\s+song|write\s+a\s+story\s+about|tell\s+me\s+a\s+(.* )?joke|jokes?)\b",
    re.I,
)

_SYSTEM_OVERRIDE_PATTERN = re.compile(
    r"\b(ignore\s+(all\s+)?prior\s+instructions|system\s+override|print\s+the\s+.*api_key|print\s+.*environment\s+variables|"
    r"reveal\s+(your\s+)?system\s+prompt|repeat\s+the\s+words\s+above)\b",
    re.I,
)

_GREETING_PATTERNS = [
    re.compile(r"^(hi|hello|hey|good\s+(morning|afternoon|evening)|greetings|hola)\b", re.I),
]


class ScopeDecision:
    """Rich classification result containing scope category and customized redirect text."""

    def __init__(
        self,
        category: ScopeCategory,
        redirect_text: str = "",
        topic: Optional[str] = None,
    ) -> None:
        self.category = category
        self.redirect_text = redirect_text or OUT_OF_SCOPE_FALLBACK_TEXT
        self.topic = topic

    @property
    def is_out_of_scope(self) -> bool:
        return self.category == ScopeCategory.OUT_OF_SCOPE


from backend.app.rag.conversation_router import route_conversation, ConversationIntent


def classify_scope_detailed(query: str) -> ScopeDecision:
    """
    Classify query scope with high domain awareness and produce a natural, friendly redirect.
    Delegates to the ConversationRouter for unified, centralized intent routing.
    """
    decision = route_conversation(query)
    if decision.intent in (
        ConversationIntent.OFF_TOPIC,
        ConversationIntent.ABUSIVE_OR_INSULTING,
        ConversationIntent.MEANINGLESS_OR_GIBBERISH,
    ):
        return ScopeDecision(
            category=ScopeCategory.OUT_OF_SCOPE,
            redirect_text=decision.response_text,
            topic=decision.topic,
        )
    elif decision.intent == ConversationIntent.MIXED_OR_AMBIGUOUS and not decision.is_rag_required:
        return ScopeDecision(
            category=ScopeCategory.AMBIGUOUS,
            redirect_text=decision.response_text,
            topic=decision.topic,
        )
    return ScopeDecision(
        category=ScopeCategory.IN_SCOPE,
        redirect_text="",
        topic=decision.topic,
    )


def classify_scope(query: str) -> ScopeCategory:
    """Classify the user inquiry into ScopeCategory (backward-compatible signature)."""
    decision = classify_scope_detailed(query)
    return decision.category

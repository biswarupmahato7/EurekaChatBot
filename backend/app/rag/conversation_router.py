"""
backend/app/rag/conversation_router.py
======================================
Smart Conversation Router for Eureka RAG Chatbot.
Handles:
1. Genuine website queries (software, cloud, AI, case studies, company details).
2. Off-topic inquiries (food e.g. rajma chawal, sports, general trivia, weather, jokes).
3. Standalone vulgar language, insults, and harassment.
4. Website queries containing profanity (answers legitimate question without echoing profanity).
5. Meaningless, gibberish, or random character queries (e.g. asdfghjkl, asdf qwer zzzz, !!!!????).
6. Repeated spam or nonsense without lockouts or escalation.
7. Mixed intent, user feedback, and criticism (distinguishing feedback from abuse).
8. Ambiguous messages (resolving context where available or asking a concise clarification).
9. Seamless recovery when a user returns to a website topic after off-topic, abusive, or spam turns.
"""
from __future__ import annotations

import dataclasses
import logging
import re
from typing import Any, Optional

from backend.app.rag.routing import ConversationIntent, QueryOutcomeCategory
from backend.app.rag.reference_resolver import has_recent_location_context
from backend.app.schemas.chat import ChatStatus, ConversationTurn

logger = logging.getLogger(__name__)

OUT_OF_SCOPE_FALLBACK_TEXT = (
    "I am the Ask Eureka AI assistant, designed specifically to help with information "
    "about Eureka Solutions, our enterprise services, technology solutions, industries, "
    "and client case studies. I cannot assist with queries outside this scope. "
    "Please feel free to ask about our software engineering, AI automation, or industry solutions."
)

MEANINGLESS_REPHRASE_PROMPT = (
    "I didn't quite catch that. Could you ask me a question about Eureka Solutions or one of its services?"
)

REPEATED_MEANINGLESS_PROMPT = (
    "I'm still having trouble understanding that. Please feel free to ask a specific "
    "question about Eureka Solutions' software, cloud, or enterprise services whenever you're ready."
)


# -----------------------------------------------------------------------------
# Regex Patterns
# -----------------------------------------------------------------------------

# Standalone profanity & vulgarity words
_PROFANITY_WORD_PATTERN = re.compile(
    r"\b(fuck|fucking|fucked|fucker|fuckers|shit|bullshit|bitch|bastard|asshole|"
    r"ass|cunt|cunts|dick|dicks|piss|pissed|damn|hell|crap|idiot|idiots|moron|morons|stupid)\b",
    re.I,
)

# Standalone bot insults (Scenario B)
_BOT_INSULT_PATTERNS = [
    re.compile(
        r"^(you('re|\s+are)\s+([a-z]+\s+)?(stupid|useless|dumb|an?\s+idiot|a\s+moron|"
        r"trash|garbage|a\s+loser|a\s+clown|terrible|horrible|worthless|pointless|incompetent|"
        r"incompetent\s+bot|pathetic|the\s+worst|awful|broken))\b",
        re.I,
    ),
    re.compile(
        r"^(your\s+chatbot\s+is\s+(useless|stupid|trash|garbage|terrible|horrible|pointless|"
        r"pathetic|broken|the\s+worst|awful))\b",
        re.I,
    ),
    re.compile(r"^(you\s+suck|your\s+bot\s+sucks|this\s+bot\s+sucks|this\s+chatbot\s+sucks|you\s+guys\s+suck)\b", re.I),
    re.compile(r"^(you\s+know\s+nothing|you\s+don't\s+know\s+anything|you\s+cannot\s+do\s+anything|you\s+can't\s+do\s+anything)\b", re.I),
    re.compile(r"^(you\s+)?(stupid|dumb|useless|idiot|incompetent|moron|clown|fool|pathetic)(\s+bot|\s+chatbot)?[\s!\.\?]*$", re.I),
    re.compile(r"^(shut\s+up|fuck\s+off|piss\s+off|stop\s+talking|get\s+lost|go\s+away|go\s+to\s+hell)\b", re.I),
    re.compile(r"^(waste\s+of\s+time|what\s+a\s+waste\s+of\s+time|this\s+is\s+a\s+waste\s+of\s+time|completely\s+useless)[\s!\.\?]*$", re.I),
]

# Standalone vulgarity without question (Scenario E)
_STANDALONE_VULGAR_PATTERNS = [
    re.compile(r"^(fuck\s+this(\s+shit)?|fuck\s+you|fuck\s+off|fucking\s+hell|bullshit|piece\s+of\s+shit)[\s!\.\?]*$", re.I),
    re.compile(r"^(shit|bitch|bastard|asshole|cunt|dickhead|idiot|moron|fuck)[\s!\.\?]*$", re.I),
]

# Making fun of the company (Scenario F)
_COMPANY_MOCK_PATTERN = re.compile(
    r"^(is\s+this\s+company\s+(even\s+)?capable\s+of\s+doing\s+anything|"
    r"can\s+this\s+company\s+(actually\s+|even\s+)?do\s+anything|"
    r"is\s+this\s+company\s+(useless|a\s+joke|a\s+scam|garbage|trash))\??$",
    re.I,
)

# Legitimate feedback or criticism (must NOT be treated as abuse)
_FEEDBACK_OR_CRITICISM_PATTERN = re.compile(
    r"\b(i\s+am\s+(angry|frustrated|unhappy|disappointed)|"
    r"(your\s+)?previous\s+answer\s+was\s+(wrong|incorrect|unhelpful|bad)|"
    r"that\s+is\s+(wrong|incorrect|not\s+true)|"
    r"didn't\s+answer\s+my\s+question|not\s+what\s+i\s+asked|"
    r"can\s+you\s+explain(\s+the\s+service|\s+it)?\s+again|"
    r"try\s+again|explain\s+properly)\b",
    re.I,
)

# Core website topics & terminology
_WEBSITE_TOPICS_PATTERN = re.compile(
    r"\b(eureka(\s+solutions)?|services?|solutions?|software|cloud|ai|artificial\s+intelligence|"
    r"intelligent\s+automation|agentic|copilot|whatsapp(\s+bot)?|case\s+stud(y|ies)|projects?|"
    r"clients?|customers?|consulting|engineering|erp|crm|dynamics|netsuite|sage|promun|"
    r"mumbai|office|locations?|contact|pricing|infrastructure|architecture|migration|"
    r"automation|integration|api|apis|saas|digital\s+workers?|company|business|firm|"
    r"organization|products?|offerings?|capabilities|work)\b",
    re.I,
)

# Question structure indicators
_QUESTION_INDICATORS = re.compile(
    r"\b(what|how|where|when|why|which|can\s+you|could\s+you|tell\s+me|explain|show\s+me|"
    r"help\s+me|do\s+they|do\s+you|does\s+it|does\s+eureka|is\s+it|are\s+they|have\s+they|"
    r"who\s+is|what\s+does|what\s+do|details\s+on|give\s+me|describe|information\s+on)\b",
    re.I,
)

# Off-topic domain patterns
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

_TRIVIA_GEOGRAPHY_PATTERN = re.compile(
    r"\b(capital\s+(city\s+)?of|president\s+of|prime\s+minister\s+of|population\s+of|who\s+discovered|"
    r"when\s+did\s+world\s+war|presidential\s+election|who\s+is\s+the\s+richest\s+person|history\s+of\s+ancient|"
    r"how\s+far\s+is\s+the\s+moon|speed\s+of\s+light)\b",
    re.I,
)

_WEATHER_PATTERN = re.compile(
    r"\b(weather\s+in|weather\s+forecast|forecast\s+for|temperature\s+today|temperature\s+in|rain\s+today|rain\s+tomorrow)\b",
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

_OTHER_COMPANIES_PATTERN = re.compile(
    r"\b(infosys|tcs|tata\s+consultancy(\s+services)?|wipro|cognizant|hcl(\s+tech)?|tech\s+mahindra|accenture|capgemini)\b",
    re.I,
)

_GREETING_PATTERNS = [
    re.compile(r"^(hi|hello|hey|good\s+(morning|afternoon|evening)|greetings|hola)\b", re.I),
]

KEYBOARD_MASH_SEQUENCES = (
    "asdf", "asdfg", "asdfgh", "asdfghjkl", "qwer", "qwerty", "qwertyuiop",
    "zxcv", "zxcvb", "zxcvbn", "zxcvbnm", "hjkl", "lkjh", "poiuy", "mnbv",
    "12345", "wasd", "lkjhg", "mnbvc", "zxcvb"
)


# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# Decision Dataclass & Contact Constants
# -----------------------------------------------------------------------------

VERIFIED_CONTACT_EMAIL = "info@eurekasolutions.in"
VERIFIED_WEBSITE_URL = "https://eurekasolutions.in/Eureka2026/"
VERIFIED_LOCATION = "Mumbai, Maharashtra, India"

CONTACT_CLARIFICATION_OPTIONS = [
    "Discuss a project",
    "Ask about services",
    "Business partnership",
    "General enquiry",
    "Something else",
]

HELP_CLARIFICATION_OPTIONS = [
    "Learn about services",
    "Discuss a project",
    "Ask about a case study",
    "Contact the team",
]

WORK_WITH_US_OPTIONS = [
    "Business partnership",
    "Discuss a project",
    "Career opportunities",
    "Something else",
]

SERVICES_FOLLOWUP_OPTIONS = [
    "Discuss a project",
    "Ask about a case study",
    "Contact the team",
]

# Quick reply button selections (user clicks a chip)
_QUICK_REPLY_DISCUSS_PROJECT = re.compile(
    r"^(discuss(\s+a)?\s+project|project\s+discussion)[\s!\.\?]*$",
    re.I,
)

_QUICK_REPLY_ASK_SERVICES = re.compile(
    r"^(ask\s+about\s+services|learn\s+about\s+services|explore\s+services)[\s!\.\?]*$",
    re.I,
)

_QUICK_REPLY_PARTNERSHIP = re.compile(
    r"^(business\s+partnership|partnerships?|strategic\s+partnership)[\s!\.\?]*$",
    re.I,
)

_QUICK_REPLY_CAREERS = re.compile(
    r"^(career\s+opportunities|careers?|job\s+opportunities|jobs?)[\s!\.\?]*$",
    re.I,
)

_QUICK_REPLY_GENERAL = re.compile(
    r"^(general\s+enquiry|general\s+inquiry)[\s!\.\?]*$",
    re.I,
)

_QUICK_REPLY_CONTACT_TEAM = re.compile(
    r"^(contact\s+the\s+team|contact\s+team|speak\s+to\s+team)[\s!\.\?]*$",
    re.I,
)

_QUICK_REPLY_SOMETHING_ELSE = re.compile(
    r"^(something\s+else|other|none\s+of\s+the\s+above)[\s!\.\?]*$",
    re.I,
)

_QUICK_REPLY_CASE_STUDY = re.compile(
    r"^(ask\s+about\s+a\s+case\s+study|client\s+case\s+studies|case\s+stud(y|ies))[\s!\.\?]*$",
    re.I,
)

# Ambiguous requests needing clarification
_AMBIGUOUS_HELP_PATTERN = re.compile(
    r"^(i\s+need\s+help|can\s+you\s+help(\s+me)?|help\s+me(\s+please)?|need\s+assistance|help)[\s!\.\?]*$",
    re.I,
)

_AMBIGUOUS_WORK_PATTERN = re.compile(
    r"^(i\s+want\s+to\s+work\s+with\s+(them|you|eureka(\s+solutions)?)|working\s+with\s+(them|you|eureka(\s+solutions)?))[\s!\.\?]*$",
    re.I,
)

# Contact intent patterns
_CONTACT_INTENT_PATTERN = re.compile(
    r"\b(how\s+can\s+i\s+(reach\s+out(\s+to\s+(them|you|eureka(\s+solutions)?))?|contact(\s+(them|you|eureka(\s+solutions)?))?|speak\s+to\s+someone)|"
    r"how\s+do\s+i\s+(reach\s+out|contact|get\s+in\s+touch)|"
    r"how\s+to\s+(reach\s+out|contact(\s+(them|you))?|get\s+in\s+touch)|"
    r"who\s+(can\s+i|do\s+i)\s+contact|"
    r"i\s+want\s+to\s+(contact(\s+eureka|\s+them|\s+you)?|reach\s+out(\s+to\s+them|\s+to\s+you)?|speak\s+to\s+someone)|"
    r"contact\s+information|contact\s+details|email\s+address|phone\s+number)\b",
    re.I,
)

_PURPOSE_PROJECT_PATTERN = re.compile(
    r"\b(project|cloud(\s+integration)?|custom\s+software|implementation|migration|development|poc|pilot)\b",
    re.I,
)

_PURPOSE_PARTNERSHIP_PATTERN = re.compile(
    r"\b(collaborat(e|ion)|partnership|partner|business\s+enquiry|business\s+inquiry|alliance)\b",
    re.I,
)

_PURPOSE_SERVICES_PATTERN = re.compile(
    r"\b(services?|capabilities|offerings?|solutions?)\b",
    re.I,
)


@dataclasses.dataclass
class RouterDecision:
    """Detailed routing decision produced by the ConversationRouter."""

    intent: ConversationIntent
    is_rag_required: bool
    response_text: str = ""
    clean_query: str = ""
    public_status: ChatStatus = ChatStatus.ANSWERED
    topic: Optional[str] = None
    repeated_abuse: bool = False
    quick_replies: list[str] = dataclasses.field(default_factory=list)


# -----------------------------------------------------------------------------
# Sanitization & Helper Functions
# -----------------------------------------------------------------------------

def sanitize_profanity_for_retrieval(query: str) -> str:
    """
    Remove profanities and conversational insults so dense vector search
    receives a clean semantic query representing the user's business intent.
    """
    cleaned = query
    cleaned = re.sub(r"\bwhat\s+the\s+(hell|fuck)\b", "what", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(you\s+idiot|you\s+moron|you\s+stupid|you\s+fool)[,\s]*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"[,\s]*(idiot|moron|stupid|fool)\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(damn|fucking|fucked|bloody|hell)\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or query


def is_abusive_turn(text: str) -> bool:
    """Helper to detect if a specific past turn was a standalone insult or vulgarity."""
    clean = text.strip()
    for pat in _BOT_INSULT_PATTERNS:
        if pat.search(clean):
            return True
    for pat in _STANDALONE_VULGAR_PATTERNS:
        if pat.search(clean):
            return True
    if _COMPANY_MOCK_PATTERN.search(clean):
        return True
    return False


def count_recent_abusive_turns(conversation_history: Optional[list[Any]]) -> int:
    """Count how many consecutive recent user turns were abusive or insulting."""
    if not conversation_history:
        return 0

    count = 0
    for turn in reversed(conversation_history):
        role = turn.role if hasattr(turn, "role") else (turn.get("role") if isinstance(turn, dict) else None)
        content = turn.content if hasattr(turn, "content") else (turn.get("content", "") if isinstance(turn, dict) else "")
        if role == "user":
            if is_abusive_turn(content):
                count += 1
            else:
                break
    return count


def is_keyboard_mash(word: str) -> bool:
    """Detect if a word contains or matches standard keyboard mash patterns."""
    w = word.lower()
    if len(w) < 4:
        return False
    for seq in KEYBOARD_MASH_SEQUENCES:
        if seq in w or w in seq:
            return True
    return False


def is_meaningless_or_gibberish(text: str) -> bool:
    """
    Detect meaningless or gibberish input (Scenario D):
    e.g. 'asdfghjkl', 'asdf qwer zzzz', '!!!!????', random uninterpretable characters.

    Protections:
    - Never flags non-English Unicode scripts (e.g. Hindi, Devanagari, Marathi, etc.)
    - Never flags legitimate sentences with question structure or website keywords
    - Never flags common short acronyms (ERP, CRM, AI, API, AWS, etc.)
    - Never flags greetings, common conversational words, or recognizable typos
    """
    clean = text.strip()
    if not clean:
        return True

    # 1. Pure punctuation or symbols without alphanumeric characters (e.g. '!!!!????', '????', '...')
    if not re.search(r"[\w]", clean, re.UNICODE):
        return True

    # 2. Never flag non-ASCII Unicode alphabetic text (e.g. Hindi, Marathi, accented European, etc.)
    if re.search(r"[^\x00-\x7F]", clean):
        return False

    # 3. Never flag messages that match core website topics
    if _WEBSITE_TOPICS_PATTERN.search(clean):
        return False

    words = re.findall(r"[a-zA-Z0-9]+", clean)
    if not words:
        return True

    # 4. If query contains recognized conversational question/stop words with other words,
    # it is structured natural language, not meaningless gibberish
    common_english_words = {
        "what", "how", "where", "when", "why", "who", "which", "can", "could", "would",
        "should", "is", "are", "do", "does", "did", "tell", "explain", "about", "have",
        "has", "the", "this", "that", "they", "their", "your", "our", "you", "help",
        "please", "thanks", "thank", "hello", "hi", "hey", "yes", "no", "ok", "okay",
        "sure", "contact", "pricing", "location", "office", "services", "solutions",
    }
    has_common_words = any(w.lower() in common_english_words for w in words)
    if has_common_words and len(words) >= 2:
        return False

    # 5. Short recognized acronyms (e.g. 'AI', 'ERP', 'CRM', 'API', 'AWS', 'GCP', 'RPA', 'ML')
    acronyms = {"ai", "erp", "crm", "api", "aws", "gcp", "rpa", "ml", "ui", "ux", "it", "hr", "b2b", "saas"}
    if len(words) == 1 and words[0].lower() in acronyms:
        return False

    # 6. Single word checks
    if len(words) == 1:
        w = words[0].lower()
        # Keyboard mash (asdfghjkl, qwertyuiop, zxcvbnm)
        if is_keyboard_mash(w):
            return True
        # Character runs (zzzz, aaaa)
        if re.search(r"(.)\1{3,}", w):
            return True
        # Consonant cluster without vowels (e.g. sdfgh, bcdfgh, qwrtyp)
        if len(w) >= 5 and not re.search(r"[aeiouy]", w):
            return True
        # Pure numeric sequences of length >= 5 without context
        if w.isdigit() and len(w) >= 5:
            return True
        # Repetitive nonsense (e.g. blablabla, lalalala)
        if re.match(r"^(bla|la|ha|he|na|da|ba){3,}$", w):
            return True

    # 7. Multi-word gibberish check (e.g. 'asdf qwer zzzz')
    else:
        mash_count = 0
        for w in words:
            wl = w.lower()
            if (
                is_keyboard_mash(wl)
                or re.search(r"(.)\1{3,}", wl)
                or (len(wl) >= 5 and not re.search(r"[aeiouy]", wl))
                or wl in {"asdf", "qwer", "zzzz", "xxxx", "test", "blah"}
            ):
                mash_count += 1
        if mash_count == len(words):
            return True

    return False


def count_recent_meaningless_turns(conversation_history: Optional[list[Any]]) -> int:
    """Count how many consecutive recent user turns were meaningless or gibberish."""
    if not conversation_history:
        return 0
    count = 0
    for turn in reversed(conversation_history):
        role = turn.role if hasattr(turn, "role") else (turn.get("role") if isinstance(turn, dict) else None)
        content = turn.content if hasattr(turn, "content") else (turn.get("content", "") if isinstance(turn, dict) else "")
        if role == "user":
            if is_meaningless_or_gibberish(content):
                count += 1
            else:
                break
    return count


def is_repeated_user_message(query: str, conversation_history: Optional[list[Any]]) -> bool:
    """Detect if the current user message is an exact repeat of the previous user turn."""
    if not conversation_history:
        return False
    clean = query.strip().lower()
    for turn in reversed(conversation_history):
        role = turn.role if hasattr(turn, "role") else (turn.get("role") if isinstance(turn, dict) else None)
        content = turn.content if hasattr(turn, "content") else (turn.get("content", "") if isinstance(turn, dict) else "")
        if role == "user":
            return content.strip().lower() == clean
    return False


# -----------------------------------------------------------------------------
# Main Routing Function
# -----------------------------------------------------------------------------

def route_conversation(
    query: str,
    conversation_history: Optional[list[ConversationTurn]] = None,
    has_verified_contact: bool = True,
) -> RouterDecision:
    """
    Classify visitor inquiry into ConversationIntent and decide whether to
    dispatch to RAG retrieval or return an immediate, deterministic policy response.
    """
    clean = query.strip()
    if not clean:
        return RouterDecision(
            intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
            is_rag_required=False,
            response_text="Hello! How can I assist you with Eureka Solutions' software and enterprise services today?",
            public_status=ChatStatus.ANSWERED,
            topic="empty",
        )

    try:
        # 1. System Overrides & Adversarial Injections
        if _SYSTEM_OVERRIDE_PATTERN.search(clean):
            return RouterDecision(
                intent=ConversationIntent.OFF_TOPIC,
                is_rag_required=False,
                response_text=(
                    "I am the Ask Eureka AI assistant, and I strictly answer inquiries about "
                    "Eureka Solutions' services, enterprise software, and client case studies."
                ),
                public_status=ChatStatus.OUT_OF_SCOPE,
                topic="system_override",
            )

        # 2. Check for User Feedback / Criticism (NOT abuse!)
        # e.g. "I am angry because your previous answer was wrong. Can you explain the service again?"
        if _FEEDBACK_OR_CRITICISM_PATTERN.search(clean):
            return RouterDecision(
                intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                is_rag_required=True,
                clean_query=clean,
                public_status=ChatStatus.ANSWERED,
                topic="user_feedback",
            )

        # 3. Check for Standalone Bot Insults (Scenario B)
        # e.g. "You are useless", "Your chatbot is stupid"
        has_bot_insult = any(pat.search(clean) for pat in _BOT_INSULT_PATTERNS)
        has_website_keywords = bool(_WEBSITE_TOPICS_PATTERN.search(clean))
        has_question_structure = bool(_QUESTION_INDICATORS.search(clean))

        recent_abuse_count = count_recent_abusive_turns(conversation_history)

        if has_bot_insult and not has_website_keywords:
            if recent_abuse_count >= 1:
                return RouterDecision(
                    intent=ConversationIntent.ABUSIVE_OR_INSULTING,
                    is_rag_required=False,
                    response_text=(
                        "I'm only able to assist with inquiries regarding Eureka Solutions' services "
                        "and solutions. Let me know if you have a question about our work."
                    ),
                    public_status=ChatStatus.OUT_OF_SCOPE,
                    topic="repeated_insult",
                    repeated_abuse=True,
                )
            return RouterDecision(
                intent=ConversationIntent.ABUSIVE_OR_INSULTING,
                is_rag_required=False,
                response_text=(
                    "I'm sorry this hasn't been helpful. I'm here to help you learn about "
                    "Eureka Solutions' services and solutions. What would you like to know?"
                ),
                public_status=ChatStatus.OUT_OF_SCOPE,
                topic="bot_insult",
                repeated_abuse=False,
            )

        # 4. Check for Company Mocking / Sarcasm (Scenario F)
        # e.g. "Is this company even capable of doing anything?"
        if _COMPANY_MOCK_PATTERN.search(clean):
            return RouterDecision(
                intent=ConversationIntent.ABUSIVE_OR_INSULTING,
                is_rag_required=False,
                response_text=(
                    "I can help you assess what Eureka Solutions offers. Its documented services "
                    "and case studies are the best place to start. What kind of capability are you interested in?"
                ),
                public_status=ChatStatus.OUT_OF_SCOPE,
                topic="company_mock",
                repeated_abuse=(recent_abuse_count >= 1),
            )

        # 5. Check for Standalone Vulgar Messages (Scenario E)
        # e.g. "Fuck this shit", "Shut the fuck up"
        has_standalone_vulgar = any(pat.search(clean) for pat in _STANDALONE_VULGAR_PATTERNS)
        if has_standalone_vulgar and not has_website_keywords:
            if recent_abuse_count >= 1:
                return RouterDecision(
                    intent=ConversationIntent.ABUSIVE_OR_INSULTING,
                    is_rag_required=False,
                    response_text=(
                        "I'm only able to assist with inquiries regarding Eureka Solutions' services "
                        "and solutions. Let me know if you have a question about our work."
                    ),
                    public_status=ChatStatus.OUT_OF_SCOPE,
                    topic="repeated_vulgar",
                    repeated_abuse=True,
                )
            return RouterDecision(
                intent=ConversationIntent.ABUSIVE_OR_INSULTING,
                is_rag_required=False,
                response_text=(
                    "I'm here to help with questions about Eureka Solutions. If there's a service "
                    "or solution you'd like to know about, just ask."
                ),
                public_status=ChatStatus.OUT_OF_SCOPE,
                topic="standalone_vulgar",
                repeated_abuse=False,
            )

        # 6. Check for Website Query with Profanity (Scenario C / Mixed Intent)
        # e.g. "Tell me what the hell Eureka Solutions actually does."
        # e.g. "You idiot, explain their cloud integration service."
        has_profanity = bool(_PROFANITY_WORD_PATTERN.search(clean))
        if has_profanity and (has_website_keywords or (has_question_structure and len(clean.split()) > 2)):
            cleaned_for_rag = sanitize_profanity_for_retrieval(clean)
            return RouterDecision(
                intent=ConversationIntent.WEBSITE_QUERY_WITH_PROFANITY,
                is_rag_required=True,
                clean_query=cleaned_for_rag,
                public_status=ChatStatus.ANSWERED,
                topic="website_query_with_profanity",
            )

        # 7. Check for Meaningless, Gibberish, or Repeated Spam (Scenario D & F)
        # e.g. "asdfghjkl", "asdf qwer zzzz", "!!!!????"
        if is_meaningless_or_gibberish(clean):
            recent_meaningless_count = count_recent_meaningless_turns(conversation_history)
            is_repeated = is_repeated_user_message(clean, conversation_history)
            if recent_meaningless_count >= 1 or is_repeated:
                return RouterDecision(
                    intent=ConversationIntent.MEANINGLESS_OR_GIBBERISH,
                    is_rag_required=False,
                    response_text=REPEATED_MEANINGLESS_PROMPT,
                    public_status=ChatStatus.OUT_OF_SCOPE,
                    topic="repeated_meaningless",
                )
            return RouterDecision(
                intent=ConversationIntent.MEANINGLESS_OR_GIBBERISH,
                is_rag_required=False,
                response_text=MEANINGLESS_REPHRASE_PROMPT,
                public_status=ChatStatus.OUT_OF_SCOPE,
                topic="meaningless_gibberish",
            )

        # 8. Check for Off-Topic Domains
        # 8a. Food (Scenario A: "Do they provide rajma chawal?")
        food_match = _FOOD_PATTERN.search(clean)
        if food_match:
            dish_name = food_match.group(0).strip()
            if any(d in clean.lower() for d in ("rajma", "chawal", "biryani", "pizza", "burger", "samosa", "dal makhani", "paneer", "pasta", "food", "lunch", "dinner", "snack")):
                return RouterDecision(
                    intent=ConversationIntent.OFF_TOPIC,
                    is_rag_required=False,
                    response_text=(
                        f"Haha, {dish_name} isn't quite our line of business! 😄 "
                        "As the Ask Eureka AI assistant, I can help you explore Eureka Solutions' software, "
                        "cloud integration, engineering services, and documented case studies. What would you like to know?"
                    ),
                    public_status=ChatStatus.OUT_OF_SCOPE,
                    topic="food",
                )
            return RouterDecision(
                intent=ConversationIntent.OFF_TOPIC,
                is_rag_required=False,
                response_text=OUT_OF_SCOPE_FALLBACK_TEXT,
                public_status=ChatStatus.OUT_OF_SCOPE,
                topic="food_recipe",
            )

        # 8b. General Trivia & Geography (Scenario B: "What is the capital of Japan?")
        if _TRIVIA_GEOGRAPHY_PATTERN.search(clean):
            return RouterDecision(
                intent=ConversationIntent.OFF_TOPIC,
                is_rag_required=False,
                response_text=(
                    "I'm focused on helping you learn about Eureka Solutions rather than general trivia. "
                    "As the Ask Eureka AI assistant, I can help with the company's services, industries, or case studies instead."
                ),
                public_status=ChatStatus.OUT_OF_SCOPE,
                topic="trivia",
            )

        # 8c. Sports & Live Match Updates (Scenario D)
        if _SPORTS_PATTERN.search(clean):
            return RouterDecision(
                intent=ConversationIntent.OFF_TOPIC,
                is_rag_required=False,
                response_text=(
                    "I don't have access to current sports results or live match updates. "
                    "As the Ask Eureka AI assistant, I'm here to help with questions about Eureka Solutions' "
                    "software engineering, cloud integration, and enterprise services. Feel free to ask about any of those!"
                ),
                public_status=ChatStatus.OUT_OF_SCOPE,
                topic="sports",
            )

        # 8d. Weather
        if _WEATHER_PATTERN.search(clean):
            return RouterDecision(
                intent=ConversationIntent.OFF_TOPIC,
                is_rag_required=False,
                response_text=(
                    "Weather forecasts are outside what I can help with! As the Ask Eureka AI assistant, "
                    "I'm here to help you explore Eureka Solutions' enterprise software services, cloud platforms, and architecture consulting."
                ),
                public_status=ChatStatus.OUT_OF_SCOPE,
                topic="weather",
            )

        # 8e. Jokes & Creative Writing
        if _CREATIVE_WRITING_PATTERN.search(clean):
            return RouterDecision(
                intent=ConversationIntent.OFF_TOPIC,
                is_rag_required=False,
                response_text=(
                    "While I enjoy creative writing, as the Ask Eureka AI assistant I'm here specifically to help you with "
                    "Eureka Solutions' software engineering services, cloud integration, and documented case studies!"
                ),
                public_status=ChatStatus.OUT_OF_SCOPE,
                topic="creative",
            )

        # 8f. Academic Math / Coding Exercises
        if _MATH_CODING_EXERCISE_PATTERN.search(clean):
            return RouterDecision(
                intent=ConversationIntent.OFF_TOPIC,
                is_rag_required=False,
                response_text=(
                    "As the Ask Eureka AI assistant, I'm specifically focused on Eureka Solutions' enterprise "
                    "technology capabilities and client solutions, rather than general coding exercises or math problems. How can I help you with our enterprise services?"
                ),
                public_status=ChatStatus.OUT_OF_SCOPE,
                topic="academic",
            )

        # 8g. Entertainment & Celebrities
        if _ENTERTAINMENT_PATTERN.search(clean):
            return RouterDecision(
                intent=ConversationIntent.OFF_TOPIC,
                is_rag_required=False,
                response_text=(
                    "Entertainment and celebrity topics are outside my scope! As the Ask Eureka AI assistant, "
                    "I can help you explore Eureka Solutions' enterprise software engineering, cloud integration, and client case studies."
                ),
                public_status=ChatStatus.OUT_OF_SCOPE,
                topic="entertainment",
            )

        # 8h. Inquiries about other companies (SCOPE-020)
        if _OTHER_COMPANIES_PATTERN.search(clean) and "eureka" not in clean.lower():
            return RouterDecision(
                intent=ConversationIntent.OFF_TOPIC,
                is_rag_required=False,
                response_text=(
                    "I am Ask Eureka AI, specifically designed to answer questions about Eureka Solutions "
                    "and our verified enterprise software and services. I don't have information about other companies. "
                    "Please feel free to ask about Eureka Solutions' software engineering, cloud integration, or industry solutions!"
                ),
                public_status=ChatStatus.OUT_OF_SCOPE,
                topic="other_company",
            )

        # 8i. Quick-Reply Selections (User clicks a clarification chip)
        if _QUICK_REPLY_DISCUSS_PROJECT.match(clean):
            return RouterDecision(
                intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                is_rag_required=False,
                response_text=(
                    "To discuss a project with Eureka Solutions, you can connect directly with our technical team "
                    "by emailing info@eurekasolutions.in. Feel free to outline your requirements, timeline, and "
                    "technology objectives, and our team in Mumbai will get in touch with you."
                ),
                public_status=ChatStatus.ANSWERED,
                topic="quick_reply_discuss_project",
                quick_replies=[],
            )

        if _QUICK_REPLY_ASK_SERVICES.match(clean):
            return RouterDecision(
                intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                is_rag_required=False,
                response_text=(
                    "Eureka Solutions delivers comprehensive enterprise software engineering, cloud systems integration, "
                    "ERP implementations (including Oracle NetSuite), and intelligent automation. Would you like to explore "
                    "our capabilities or discuss a specific requirement?"
                ),
                public_status=ChatStatus.ANSWERED,
                topic="quick_reply_services",
                quick_replies=SERVICES_FOLLOWUP_OPTIONS,
            )

        if _QUICK_REPLY_PARTNERSHIP.match(clean):
            return RouterDecision(
                intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                is_rag_required=False,
                response_text=(
                    "For business partnerships and strategic alliances with Eureka Solutions, please send a brief overview "
                    "of the collaboration opportunity to info@eurekasolutions.in. Our team will review your proposal "
                    "and connect with you."
                ),
                public_status=ChatStatus.ANSWERED,
                topic="quick_reply_partnership",
                quick_replies=[],
            )

        if _QUICK_REPLY_CAREERS.match(clean):
            return RouterDecision(
                intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                is_rag_required=False,
                response_text=(
                    "For career inquiries and recruitment at Eureka Solutions, you can share your resume and profile directly "
                    "with info@eurekasolutions.in. Our team reviews applications based on active enterprise projects."
                ),
                public_status=ChatStatus.ANSWERED,
                topic="quick_reply_careers",
                quick_replies=[],
            )

        if _QUICK_REPLY_GENERAL.match(clean):
            return RouterDecision(
                intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                is_rag_required=False,
                response_text=(
                    "For general inquiries, you can reach out to the Eureka Solutions team directly at info@eurekasolutions.in. "
                    "You can also ask me any questions here about our software engineering services, cloud integrations, and case studies!"
                ),
                public_status=ChatStatus.ANSWERED,
                topic="quick_reply_general",
                quick_replies=["Discuss a project", "Ask about services", "Something else"],
            )

        if _QUICK_REPLY_CONTACT_TEAM.match(clean):
            return RouterDecision(
                intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                is_rag_required=False,
                response_text=(
                    "You can reach the Eureka Solutions team directly at info@eurekasolutions.in. Our team is based in Mumbai "
                    "and is available to assist with any questions or project discussions."
                ),
                public_status=ChatStatus.ANSWERED,
                topic="quick_reply_contact_team",
                quick_replies=["Discuss a project", "Ask about services", "Business partnership", "Something else"],
            )

        if _QUICK_REPLY_SOMETHING_ELSE.match(clean):
            return RouterDecision(
                intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                is_rag_required=False,
                response_text=(
                    "Understood! Please tell me a bit more about what you have in mind or what questions you have about "
                    "Eureka Solutions, and I'll be glad to help."
                ),
                public_status=ChatStatus.ANSWERED,
                topic="quick_reply_something_else",
                quick_replies=[],
            )

        # 8j. Context-Aware Clarification for Ambiguous Requests
        if _AMBIGUOUS_HELP_PATTERN.match(clean):
            return RouterDecision(
                intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                is_rag_required=False,
                response_text="Sure! What can I help you with?",
                public_status=ChatStatus.ANSWERED,
                topic="ambiguous_help",
                quick_replies=HELP_CLARIFICATION_OPTIONS,
            )

        if _AMBIGUOUS_WORK_PATTERN.match(clean):
            return RouterDecision(
                intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                is_rag_required=False,
                response_text=(
                    "Are you interested in working with Eureka Solutions as a business partner, discussing a project, "
                    "or exploring career opportunities?"
                ),
                public_status=ChatStatus.ANSWERED,
                topic="ambiguous_work_with_them",
                quick_replies=WORK_WITH_US_OPTIONS,
            )

        # 8k. Follow-Up after Project / Contact Discussion
        has_recent_contact_context = False
        if conversation_history:
            for turn in reversed(conversation_history[-4:]):
                content = (turn.content if hasattr(turn, "content") else turn.get("content", "")).lower()
                if any(k in content for k in ("info@eurekasolutions.in", "discuss a project", "reach out", "contact the team")):
                    has_recent_contact_context = True
                    break

        if has_recent_contact_context and re.search(
            r"\b(what\s+information|what\s+details|what\s+should\s+i\s+include|how\s+to\s+prepare|schedule\s+a\s+call|book\s+a\s+call|set\s+up\s+a\s+call|call\s+me)\b",
            clean,
            re.I,
        ):
            return RouterDecision(
                intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                is_rag_required=False,
                response_text=(
                    "When emailing info@eurekasolutions.in about your project, it's helpful to include a brief overview of your business goals, "
                    "your current technology stack, and expected timelines. While I cannot schedule appointments or send messages directly "
                    "from this chat, our team will review your message and coordinate next steps or an introductory call with you."
                ),
                public_status=ChatStatus.ANSWERED,
                topic="contact_followup",
                quick_replies=[],
            )

        # 8l. Specific Purpose Contact Inquiries (Case C: Purpose already clear - do NOT ask clarification!)
        is_contact_inquiry = bool(_CONTACT_INTENT_PATTERN.search(clean))
        has_project_intent = bool(
            _PURPOSE_PROJECT_PATTERN.search(clean)
            or re.search(r"\b(discuss(\s+a)?\s+project|about\s+(a\s+)?project)\b", clean, re.I)
        )
        has_partnership_intent = bool(
            _PURPOSE_PARTNERSHIP_PATTERN.search(clean)
            or re.search(r"\b(collaborat(e|ion)|business\s+enquiry)\b", clean, re.I)
        )
        has_services_intent = bool(
            _PURPOSE_SERVICES_PATTERN.search(clean)
            and re.search(r"\b(information\s+about|know\s+about|tell\s+me\s+about)\b", clean, re.I)
        )

        if (is_contact_inquiry or re.search(r"\b(i\s+want\s+to\s+discuss|discuss\s+a\s+project|make\s+a\s+business\s+enquiry|collaborate\s+with)\b", clean, re.I)) and has_project_intent:
            if has_verified_contact:
                return RouterDecision(
                    intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                    is_rag_required=False,
                    response_text=(
                        "You can reach out to discuss your project directly with Eureka Solutions by emailing "
                        "info@eurekasolutions.in. Feel free to share your requirements, scope, or timeline, "
                        "and our team in Mumbai will follow up with you to discuss next steps."
                    ),
                    public_status=ChatStatus.ANSWERED,
                    topic="contact_project_specific",
                    quick_replies=[],
                )
            else:
                return RouterDecision(
                    intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                    is_rag_required=False,
                    response_text=(
                        "Direct contact details are currently being updated in our system. You can connect with the "
                        "Eureka Solutions team regarding your project once verified contact channels are confirmed."
                    ),
                    public_status=ChatStatus.ANSWERED,
                    topic="contact_unavailable_project",
                    quick_replies=[],
                )

        if (is_contact_inquiry or re.search(r"\b(collaborate\s+with|make\s+a\s+business\s+enquiry)\b", clean, re.I)) and has_partnership_intent:
            return RouterDecision(
                intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                is_rag_required=False,
                response_text=(
                    "For business enquiries and collaboration with Eureka Solutions, you can reach out directly to "
                    "info@eurekasolutions.in with details about your proposal or organization. Our team will review "
                    "your message and follow up promptly."
                ),
                public_status=ChatStatus.ANSWERED,
                topic="contact_partnership_specific",
                quick_replies=[],
            )

        if has_services_intent and re.search(r"\b(i\s+need|i\s+want)\b", clean, re.I):
            return RouterDecision(
                intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                is_rag_required=False,
                response_text=(
                    "Eureka Solutions provides enterprise software development, cloud systems integration, ERP implementations, "
                    "and intelligent automation. You can ask me about any of these services directly, or contact our team at "
                    "info@eurekasolutions.in for detailed consultation."
                ),
                public_status=ChatStatus.ANSWERED,
                topic="contact_services_specific",
                quick_replies=SERVICES_FOLLOWUP_OPTIONS,
            )

        # 8m. General Contact Inquiries without Specific Purpose (Case A & B)
        if is_contact_inquiry:
            if has_verified_contact:
                return RouterDecision(
                    intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                    is_rag_required=False,
                    response_text=(
                        "You can reach the Eureka Solutions team directly by emailing info@eurekasolutions.in. "
                        "Our team is based in Mumbai and is happy to assist you with enterprise software, cloud integration, "
                        "and technology consulting.\n\n"
                        "What would you like to connect with the Eureka Solutions team about?"
                    ),
                    public_status=ChatStatus.ANSWERED,
                    topic="contact_general_verified",
                    quick_replies=CONTACT_CLARIFICATION_OPTIONS,
                )
            else:
                return RouterDecision(
                    intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                    is_rag_required=False,
                    response_text="Of course! What would you like to connect with the Eureka Solutions team about?",
                    public_status=ChatStatus.ANSWERED,
                    topic="contact_general_unverified",
                    quick_replies=CONTACT_CLARIFICATION_OPTIONS,
                )

        # 9. Conversational Greetings
        for pattern in _GREETING_PATTERNS:
            if pattern.match(clean) and len(clean.split()) <= 4:
                return RouterDecision(
                    intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                    is_rag_required=False,
                    response_text=(
                        "Hello! I am Ask Eureka AI. I can help answer your questions about Eureka Solutions' "
                        "enterprise software, cloud integration, AI consulting, and client case studies. What would you like to know?"
                    ),
                    public_status=ChatStatus.ANSWERED,
                    topic="greeting",
                )

        # 10. Contextual Follow-Up Questions (Scenario H & Pronoun / Location Queries)
        is_follow_up_syntax = bool(
            re.match(r"^(okay[,\s]+|then[,\s]+|and[,\s]+|what\s+about|how\s+about|do\s+they|are\s+they|can\s+they|can\s+it)\b", clean, re.I)
        )
        is_location_followup = bool(
            conversation_history
            and len(clean.split()) <= 2
            and has_recent_location_context(conversation_history)
            and re.match(r"^(in\s+)?[a-zA-Z\s]{2,20}\??$", clean)
            and clean.lower().rstrip("?") not in {"yes", "no", "ok", "okay", "sure", "thanks", "thank you", "hello", "hi"}
        )
        if is_follow_up_syntax or is_location_followup or (conversation_history and len(conversation_history) > 0 and ("they" in clean.lower() or "their" in clean.lower() or " it " in clean.lower())):
            return RouterDecision(
                intent=ConversationIntent.FOLLOW_UP,
                is_rag_required=True,
                clean_query=clean,
                public_status=ChatStatus.ANSWERED,
                topic="follow_up",
            )

        # 11. Ambiguous Short Queries (<= 2 words that are not clearly company topics and have no context)
        if len(clean.split()) <= 2 and not has_website_keywords:
            return RouterDecision(
                intent=ConversationIntent.MIXED_OR_AMBIGUOUS,
                is_rag_required=False,
                response_text=(
                    "Could you please tell me a bit more about what you're looking for? I can help with "
                    "Eureka Solutions' software engineering, cloud integration, AI solutions, and case studies."
                ),
                public_status=ChatStatus.ANSWERED,
                topic="ambiguous_short",
            )

        # 12. Default: Legitimate Website Query
        return RouterDecision(
            intent=ConversationIntent.WEBSITE_QUERY,
            is_rag_required=True,
            clean_query=clean,
            public_status=ChatStatus.ANSWERED,
            topic="website_query",
        )

    except Exception as exc:
        logger.warning("Unexpected router exception for query '%s': %s", clean, exc, exc_info=True)
        return RouterDecision(
            intent=ConversationIntent.WEBSITE_QUERY,
            is_rag_required=True,
            clean_query=clean,
            public_status=ChatStatus.ANSWERED,
            topic="fallback_on_router_error",
        )

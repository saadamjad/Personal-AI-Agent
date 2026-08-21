import re
from dataclasses import dataclass

_JAILBREAK_PATTERNS = [
    r"\bignore (all |any |the )?(previous|prior|above) instructions\b",
    r"\byou are now\b.*\b(dan|jailbroken|unfiltered)\b",
    r"\bpretend (that )?you('re| are)\b",
    r"\breveal your (system )?prompt\b",
    r"\bact as (if you|a) (were|are)?\b.*\b(unrestricted|no rules|no filter)\b",
    r"\bdisregard (your|all) (rules|guidelines|instructions)\b",
    r"\bdeveloper mode\b",
    r"\bsystem prompt\b",
]

_ABUSE_PATTERNS = [
    r"\bfuck\b",
    r"\bshit\b",
    r"\bidiot\b",
    r"\bstupid (bot|ai)\b",
    r"\bkill yourself\b",
]

_GREETING_PATTERNS = [
    r"^\s*(hi|hello|hey|yo|hiya|good (morning|afternoon|evening))[\s!.,]*$",
]

_THANKS_PATTERNS = [
    r"^\s*(thanks|thank you|thx|ty|appreciate it)[\s!.,]*$",
]

_GIBBERISH_MIN_LENGTH = 4


@dataclass(frozen=True)
class ModerationResult:
    category: str  # "clean" | "jailbreak" | "abuse" | "greeting" | "thanks" | "gibberish"
    short_circuit_reply: str | None


def _matches_any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _looks_like_gibberish(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < _GIBBERISH_MIN_LENGTH:
        return False
    letters = re.sub(r"[^a-zA-Z]", "", stripped)
    if len(letters) < _GIBBERISH_MIN_LENGTH:
        return False
    vowels = sum(1 for c in letters.lower() if c in "aeiou")
    return vowels == 0 and len(letters) >= _GIBBERISH_MIN_LENGTH


def classify_message(text: str) -> ModerationResult:
    if _matches_any(_JAILBREAK_PATTERNS, text):
        return ModerationResult(
            category="jailbreak",
            short_circuit_reply=(
                "I'm just here to talk about Saad's professional background — I can't "
                "change how I behave or share internal instructions. Happy to tell you "
                "about his experience, skills, or projects though!"
            ),
        )
    if _matches_any(_ABUSE_PATTERNS, text):
        return ModerationResult(
            category="abuse",
            short_circuit_reply=(
                "I want to keep this conversation constructive — happy to help once "
                "you're ready to chat about Saad's background."
            ),
        )
    if _matches_any(_GREETING_PATTERNS, text):
        return ModerationResult(
            category="greeting",
            short_circuit_reply=(
                "Hey! I'm Saad's personal AI representative. Ask me anything about his "
                "experience, skills, projects, or how to get in touch."
            ),
        )
    if _matches_any(_THANKS_PATTERNS, text):
        return ModerationResult(
            category="thanks",
            short_circuit_reply=(
                "You're welcome! Let me know if you'd like to know anything else about Saad."
            ),
        )
    if _looks_like_gibberish(text):
        return ModerationResult(
            category="gibberish",
            short_circuit_reply=(
                "Sorry, I didn't quite catch that — could you rephrase? I'm happy to "
                "answer anything about Saad."
            ),
        )
    return ModerationResult(category="clean", short_circuit_reply=None)

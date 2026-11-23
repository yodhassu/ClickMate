"""Small pure-python helpers (no GUI/audio imports, so they are easy to test)."""
import re

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_MARKDOWN = re.compile(r"[*_`#>]+")
_NOISE = re.compile(r"\[[^\]]*\]|\([^)]*\)")   # whisper tags like [BLANK_AUDIO], (silence)


def split_sentences(buffer: str):
    """Return (complete_sentences, remainder) so TTS can start before the model finishes."""
    parts = _SENTENCE_END.split(buffer)
    return [p for p in parts[:-1] if p.strip()], parts[-1]


def clean_for_speech(text: str) -> str:
    return re.sub(r"\s+", " ", _MARKDOWN.sub("", text)).strip()


def clean_transcript(text: str) -> str:
    return re.sub(r"\s+", " ", _NOISE.sub(" ", text)).strip()


_POINT_WORDS = re.compile(
    r"\b(where|which|click|press|tap|select|choose|open|find|locate|show me|point|"
    r"button|menu|icon|tab|link|option|setting|toolbar|how (do|can|to) i)\b", re.I)


def wants_pointer(question: str) -> bool:
    """True when the user is asking WHERE something is / what to click, so point first."""
    return bool(_POINT_WORDS.search(question))

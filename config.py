"""Central settings for Clicky Mini. Override anything with environment variables."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_dotenv():
    """Reads KEY=VALUE lines from ./.env into the environment (real environment variables win).
    This is where your Gemini key lives, so it never ends up inside the source code."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# --- Which AI brain to use: "ollama" (local, offline) or "gemini" (cloud, free tier) ---
# Priority: CLICKY_PROVIDER env var / .env  >  the choice saved from the tray menu  >  ollama
SETTINGS_FILE = ROOT / "settings.json"
PROVIDERS = ("ollama", "gemini")


def _saved_provider():
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8")).get("provider")
    except Exception:
        return None


def save_provider(name: str):
    """Remembers the tray-menu choice for the next start."""
    try:
        SETTINGS_FILE.write_text(json.dumps({"provider": name}), encoding="utf-8")
    except OSError:
        pass


PROVIDER = (os.getenv("CLICKY_PROVIDER") or _saved_provider() or "ollama").strip().lower()
if PROVIDER not in PROVIDERS:
    PROVIDER = "ollama"

# --- Gemini (Google AI Studio free key: https://aistudio.google.com/apikey) ---
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or os.getenv("CLICKY_GEMINI_KEY") or "").strip()
GEMINI_MODEL = os.getenv("CLICKY_GEMINI_MODEL", "gemini-3.5-flash-lite")   # any Gemini model your key can use
GEMINI_HOST = os.getenv("CLICKY_GEMINI_HOST", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")

# --- Ollama (local backend) ---
OLLAMA_HOST = os.getenv("CLICKY_OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("CLICKY_MODEL", "llava:7b")   # any vision model you have pulled
KEEP_ALIVE = "10m"                                      # keep the model loaded between questions

# --- whisper.cpp (listening) ---
# setup_whisper.ps1 puts these two files under ./whisper
WHISPER_EXE = Path(os.getenv("CLICKY_WHISPER_EXE", ROOT / "whisper" / "whisper-cli.exe"))
WHISPER_MODEL = Path(os.getenv("CLICKY_WHISPER_MODEL", ROOT / "whisper" / "models" / "ggml-base.en.bin"))
WHISPER_LANG = os.getenv("CLICKY_LANG", "en")           # use "auto" with a multilingual model (ggml-base.bin)
WHISPER_THREADS = int(os.getenv("CLICKY_THREADS", "4"))

# --- Windows built-in TTS (SAPI5) ---
TTS_RATE = int(os.getenv("CLICKY_TTS_RATE", "0"))       # -10 (slow) .. 10 (fast)
TTS_VOLUME = int(os.getenv("CLICKY_TTS_VOLUME", "100")) # 0 .. 100

# --- Pointing ---
# Gemini points directly (one call, no grid). The settings below only matter for Ollama's grid locator.
LOCATOR_STAGES = int(os.getenv("CLICKY_LOCATOR_STAGES", "3"))   # zoom rounds; more = more precise, slower
LOCATOR_WIDTH = int(os.getenv("CLICKY_LOCATOR_WIDTH", "768"))   # size the model sees each round (llava reads ~672px;
                                                                # bigger models such as qwen2.5vl can take 1280)

# --- Behaviour ---
MAX_IMAGE_WIDTH = 1280        # screenshots are downscaled before going to the model
HISTORY_TURNS = int(os.getenv("CLICKY_HISTORY", "0"))  # earlier Q&A pairs sent along. 0 = every question
                                                       # is judged on a fresh screenshot (llava gets stuck on old answers otherwise)
MIN_RECORD_SECONDS = 0.4      # ignore accidental taps of the hotkey
POINT_SECONDS = 10            # how long the blue cursor stays on screen

SYSTEM_PROMPT = (
    "You are Clicky, a friendly tutor who can see the user's screen. "
    "The user asks a question out loud while looking at the screenshot. "
    "Answer in at most three short, plain sentences, exactly as you would say them aloud. "
    "No markdown, no lists, no emojis. Name the buttons, menus or text you are referring to. "
    "Never say that you cannot see the screen. "
    "Always answer from the screenshot attached to the CURRENT message, never from earlier answers."
)

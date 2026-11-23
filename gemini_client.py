"""Gemini client (plain HTTP, no SDK). Same interface as llm.OllamaClient, plus native pointing.

Why Gemini is better at pointing: it is trained to return the position of things in a picture.
We ask for a bounding box `box_2d = [ymin, xmin, ymax, xmax]` on a 0-1000 scale, so ONE call
replaces the three-round grid game that small local models need.

Get a free key (no credit card): https://aistudio.google.com/apikey  ->  put it in .env
"""
import json
import re
from typing import Optional, Tuple

import requests
from PIL import Image

import config
import llm


# ------------------------------------------------------------------ pure helpers (unit-tested)
def to_gemini_contents(messages):
    """Ollama-style messages -> (system_text, Gemini "contents").

    {"role": "system"|"user"|"assistant", "content": str, "images": [base64 jpeg, ...]}
    """
    system_parts, contents = [], []
    for m in messages:
        role, text = m.get("role"), m.get("content", "")
        if role == "system":
            system_parts.append(text)
            continue
        parts = [{"text": text}]
        for b64 in m.get("images", []) or []:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
        contents.append({"role": "model" if role == "assistant" else "user", "parts": parts})
    return "\n".join(system_parts), contents


def _numbers_ok(values, n):
    return (isinstance(values, (list, tuple)) and len(values) == n
            and all(isinstance(v, (int, float)) and 0 <= v <= 1000 for v in values))


def _find_target(node):
    """Search parsed JSON for a box_2d (4 numbers) or point (2 numbers). Returns (fx, fy) or None."""
    if isinstance(node, dict):
        box = node.get("box_2d") or node.get("box")
        if _numbers_ok(box, 4):
            ymin, xmin, ymax, xmax = box
            return (xmin + xmax) / 2000.0, (ymin + ymax) / 2000.0
        point = node.get("point")
        if _numbers_ok(point, 2):
            y, x = point
            return x / 1000.0, y / 1000.0
        for value in node.values():
            found = _find_target(value)
            if found:
                return found
    elif isinstance(node, list):
        if _numbers_ok(node, 4):                   # a bare [ymin, xmin, ymax, xmax]
            ymin, xmin, ymax, xmax = node
            return (xmin + xmax) / 2000.0, (ymin + ymax) / 2000.0
        for value in node:
            found = _find_target(value)
            if found:
                return found
    return None


def parse_target(text: str) -> Optional[Tuple[float, float]]:
    """Gemini's reply -> centre of the box as fractions (0..1) of the screenshot, or None.

    None means "nothing to point at" (or an unreadable reply).
    """
    cleaned = re.sub(r"```(?:json)?", "", text or "").strip()
    found, is_json = None, True
    try:
        found = _find_target(json.loads(cleaned))
    except (ValueError, TypeError):
        is_json = False
    if found is None and not is_json:              # not JSON at all: first four numbers in the text
        nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", cleaned)[:4]]
        if _numbers_ok(nums, 4):
            found = _find_target(nums)
    if found is None:
        return None
    return min(1.0, max(0.0, found[0])), min(1.0, max(0.0, found[1]))


def _error_text(resp) -> str:
    try:
        return resp.json().get("error", {}).get("message", resp.text)
    except Exception:
        return resp.text


def _check(resp):
    """Turn HTTP errors into messages a student can act on."""
    if resp.status_code < 400:
        return
    detail = _error_text(resp)[:300]
    code = resp.status_code
    if code == 429:
        raise RuntimeError("Gemini free quota reached (too many requests). Wait a minute, "
                           "or switch to Ollama from the tray icon.")
    if code in (400, 403) and ("API key" in detail or "API_KEY" in detail or code == 403):
        raise RuntimeError(f"Gemini rejected the API key ({code}). Check GEMINI_API_KEY in .env. {detail}")
    if code == 404:
        raise RuntimeError(f"Gemini model '{config.GEMINI_MODEL}' not found. "
                           f"Set CLICKY_GEMINI_MODEL to a model your key can use. {detail}")
    raise RuntimeError(f"Gemini {code}: {detail}")


# ------------------------------------------------------------------ the client
class GeminiClient:
    name = "gemini"
    native_pointing = True

    def __init__(self, api_key: str = None, model: str = None, host: str = None):
        self.api_key = api_key if api_key is not None else config.GEMINI_API_KEY
        self.model = model or config.GEMINI_MODEL
        self.host = (host or config.GEMINI_HOST).rstrip("/")

    @property
    def label(self) -> str:
        return f"Gemini ({self.model})"

    def _headers(self):
        return {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def _gen_config(self, **extra):
        cfg = {"temperature": 0.3}
        # Gemini 2.5 Flash "thinks" before answering, which adds seconds. Voice answers do not need it.
        if "2.5-flash" in self.model:
            cfg["thinkingConfig"] = {"thinkingBudget": 0}
        cfg.update(extra)
        return cfg

    def _body(self, messages, **gen_extra):
        system, contents = to_gemini_contents(messages)
        body = {"contents": contents, "generationConfig": self._gen_config(**gen_extra)}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        return body

    # ---- health ----
    def check(self):
        """Returns a list of problems (empty list = all good)."""
        if not self.api_key:
            return ["No Gemini key. Get a free one at https://aistudio.google.com/apikey "
                    "and put GEMINI_API_KEY=... in the .env file."]
        try:
            resp = requests.get(f"{self.host}/models/{self.model}", headers=self._headers(), timeout=6)
        except requests.RequestException:
            return ["Cannot reach Gemini - check your internet connection."]
        try:
            _check(resp)
        except RuntimeError as exc:
            return [str(exc)]
        return []

    def warmup(self):
        """Nothing to load for a cloud model."""

    # ---- chat ----
    def stream_chat(self, messages):
        """Yield text pieces as the model writes them."""
        resp = requests.post(
            f"{self.host}/models/{self.model}:streamGenerateContent?alt=sse",
            headers=self._headers(), json=self._body(messages), stream=True, timeout=(10, 120),
        )
        _check(resp)
        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace")
            if not line.startswith("data:"):
                continue
            obj = json.loads(line[5:].strip())
            if "error" in obj:
                raise RuntimeError(obj["error"].get("message", str(obj["error"])))
            block = obj.get("promptFeedback", {}).get("blockReason")
            if block:
                raise RuntimeError(f"Gemini blocked this request ({block}).")
            for cand in obj.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    if part.get("text") and not part.get("thought"):
                        yield part["text"]

    def _generate(self, messages, **gen_extra) -> str:
        resp = requests.post(
            f"{self.host}/models/{self.model}:generateContent",
            headers=self._headers(), json=self._body(messages, **gen_extra), timeout=(10, 60),
        )
        _check(resp)
        data = resp.json()
        texts = []
        for cand in data.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                if part.get("text") and not part.get("thought"):
                    texts.append(part["text"])
        return "".join(texts)

    def ask_images(self, prompt: str, images, max_tokens: int = 30) -> str:
        """One-shot question about PIL images (same interface as the Ollama client)."""
        msg = {"role": "user", "content": prompt, "images": [llm.pil_to_b64(i, 85) for i in images]}
        return self._generate([msg], temperature=0, maxOutputTokens=max(max_tokens, 64))

    # ---- native pointing ----
    def point(self, image: Image.Image, query: str, allow_none: bool = True):
        """Where on the screenshot should the user look/click? Returns (fx, fy) in 0..1, or None."""
        if allow_none:
            ending = ('If the question is general and there is no specific element to point at, '
                      'reply exactly {"box_2d": null}.')
        else:
            ending = "The element IS on the screen. If unsure, give your best guess. Never reply null."
        prompt = (
            "This is a screenshot of a computer screen.\n"
            f'The user asked: "{query}"\n'
            "Find the ONE button, menu, icon, link, tab or text box the user needs to click or look at, "
            "and give its bounding box.\n"
            'Reply with ONLY JSON like {"box_2d": [ymin, xmin, ymax, xmax], "label": "short name"} '
            "with coordinates normalised to 0-1000 (0,0 = top-left corner, 1000,1000 = bottom-right corner).\n"
            + ending
        )
        msg = {"role": "user", "content": prompt, "images": [llm.pil_to_b64(llm.downscale(image), 85)]}
        reply = self._generate([msg], temperature=0, maxOutputTokens=1024,
                               responseMimeType="application/json")
        target = parse_target(reply)
        if target is None:
            print(f"[locator] gemini returned no box: {reply[:150]!r}")
        return target

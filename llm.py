"""Tiny Ollama client (plain HTTP, no SDK). Ollama is the only model backend."""
import base64
import io
import json

import requests
from PIL import Image

import config


def pil_to_b64(img: Image.Image, quality: int = 80) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def downscale(img: Image.Image, max_width: int = config.MAX_IMAGE_WIDTH) -> Image.Image:
    if img.width <= max_width:
        return img
    ratio = max_width / img.width
    return img.resize((max_width, int(img.height * ratio)), Image.Resampling.LANCZOS)


def _check(resp):
    """Raise an error that includes Ollama's own message (e.g. "model 'x' not found")."""
    if resp.status_code >= 400:
        try:
            msg = resp.json().get("error", resp.text)
        except Exception:
            msg = resp.text
        raise RuntimeError(f"Ollama {resp.status_code}: {msg}")


class OllamaClient:
    name = "ollama"
    native_pointing = False     # small local models need the zoom-grid locator

    def __init__(self, host: str = config.OLLAMA_HOST, model: str = config.OLLAMA_MODEL):
        self.host = host
        self.model = model

    @property
    def label(self) -> str:
        return f"Ollama ({self.model})"

    # ---- health ----
    def check(self):
        """Returns a list of problems (empty list = all good)."""
        try:
            tags = requests.get(f"{self.host}/api/tags", timeout=3).json()
        except Exception:
            return [f"Cannot reach Ollama at {self.host} - is it running? (try: ollama serve)"]
        names = {m.get("name", "") for m in tags.get("models", [])}
        if self.model not in names and f"{self.model}:latest" not in names:
            return [f"Model '{self.model}' is not pulled - run: ollama pull {self.model}"]
        return []

    def warmup(self):
        """Load the model into memory so the first real question is faster."""
        try:
            requests.post(f"{self.host}/api/generate",
                          json={"model": self.model, "keep_alive": config.KEEP_ALIVE}, timeout=120)
        except Exception:
            pass

    # ---- chat ----
    def stream_chat(self, messages):
        """Yield text pieces as the model writes them."""
        resp = requests.post(
            f"{self.host}/api/chat",
            json={"model": self.model, "messages": messages, "stream": True,
                  "keep_alive": config.KEEP_ALIVE, "options": {"temperature": 0.3}},
            stream=True, timeout=(5, 300),
        )
        _check(resp)
        for line in resp.iter_lines():
            if not line:
                continue
            obj = json.loads(line)
            if "error" in obj:
                raise RuntimeError(obj["error"])
            piece = obj.get("message", {}).get("content", "")
            if piece:
                yield piece
            if obj.get("done"):
                break

    def ask_images(self, prompt: str, images, max_tokens: int = 30) -> str:
        """One-shot, non-streaming question about one or more PIL images (used by the locator)."""
        resp = requests.post(
            f"{self.host}/api/chat",
            json={"model": self.model, "stream": False, "keep_alive": config.KEEP_ALIVE,
                  "messages": [{"role": "user", "content": prompt,
                                "images": [pil_to_b64(i, 85) for i in images]}],
                  "options": {"temperature": 0, "num_predict": max_tokens}},
            timeout=(5, 300),
        )
        _check(resp)
        return resp.json().get("message", {}).get("content", "")

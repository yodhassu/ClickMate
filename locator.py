"""Finds WHERE on the screen to point.

Two strategies, chosen automatically by the AI provider in use:
  * Gemini (native_pointing = True): one call that returns the element's bounding box.
  * Ollama (small local models): the zoom-in grid locator described below.

Zoom-in grid locator: how a small local vision model "points" at something.

Small models are bad at returning pixel coordinates and bad at reading lots of tiny grid
numbers. They ARE good at picking one of nine big labelled cells. So we play "hot and cold":

  round 1: show the whole screen split into a 3x3 grid (cells 1-9) -> the model picks a cell
  round 2: zoom into that cell (plus a little padding) -> another 3x3 grid -> pick again
  round 3: zoom again -> pick again
  answer : the centre of the last chosen cell

Three rounds narrow the screen to about 8% of its width (about +-25 px on a 1920 px screen).
The result is returned as FRACTIONS of the screen (0..1), so it works at any resolution.

Idea follows Bitshank-2338/clicky-windows (MIT) via AbhishekVulla/clicky-windows, with big
3x3 rounds instead of a 12x8 grid because small models cannot read dozens of tiny labels.
"""
import json
import re
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

import config

GRID = 3
PAD = 0.15   # zoom region = chosen cell + 15% of a cell on each side, so edge cases still fit


def _font(size):
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def draw_grid(img: Image.Image, cols: int = GRID, rows: int = GRID) -> Image.Image:
    """Red grid with BIG numbers in the top-left corner of each cell."""
    base = img.convert("RGBA")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    w, h = base.size
    cw, ch = w / cols, h / rows
    line = max(2, w // 220)
    for c in range(1, cols):
        d.line([(int(c * cw), 0), (int(c * cw), h)], fill=(255, 0, 0, 230), width=line)
    for r in range(1, rows):
        d.line([(0, int(r * ch)), (w, int(r * ch))], fill=(255, 0, 0, 230), width=line)
    font = _font(max(18, int(min(cw, ch) * 0.38)))
    n = 1
    for r in range(rows):
        for c in range(cols):
            x, y = int(c * cw) + 6, int(r * ch) + 4
            box = d.textbbox((x, y), str(n), font=font)
            d.rectangle([box[0] - 4, box[1] - 3, box[2] + 5, box[3] + 4], fill=(255, 0, 0, 235))
            d.text((x, y), str(n), fill=(255, 255, 255, 255), font=font)
            n += 1
    return Image.alpha_composite(base, layer).convert("RGB")


def parse_cell(text: str, max_n: int) -> Optional[int]:
    """0 = 'nothing to point at', 1..max_n = a cell, None = unreadable reply."""
    m = re.search(r"\{[^{}]*\}", text, flags=re.DOTALL)
    if m:
        try:
            value = json.loads(m.group(0)).get("cell")
            if value is not None and 0 <= int(value) <= max_n:
                return int(value)
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
    for token in re.findall(r"\b(\d{1,3})\b", text):
        if 0 <= int(token) <= max_n:
            return int(token)
    return None


def _ask(llm, grid_img, query, allow_none=True, zoomed=False) -> Optional[int]:
    if allow_none:
        ending = 'If there is nothing specific to point at, reply exactly: {"cell": 0}'
    else:
        ending = ("The element IS visible. If you are unsure, give your best guess. "
                  "Never answer 0.")
    where = "This is a zoomed-in part of the screen. " if zoomed else ""
    prompt = (
        f"{where}The image is split by red lines into 9 cells with big red numbers: "
        f"top row 1 2 3, middle row 4 5 6, bottom row 7 8 9.\n"
        f'The user asked: "{query}"\n'
        f"Which SINGLE cell contains the thing the user needs to click or look at "
        f"(button, menu, icon, link, text box)?\n"
        'Reply with ONLY this JSON: {"cell": <number>}\n' + ending
    )
    try:
        reply = llm.ask_images(prompt, [grid_img])
    except Exception as exc:   # show the real reason instead of failing silently
        print(f"[locator] model call failed: {exc}")
        return None
    parsed = parse_cell(reply, GRID * GRID)
    if parsed is None:
        print(f"[locator] could not read a cell number from the reply: {reply[:120]!r}")
    if parsed == 0 and not allow_none:
        parsed = None
    return parsed


def _pick(llm, grid_img, query, allow_none, zoomed):
    """One answer, or two tries when we know the thing must be on screen."""
    for _ in range(1 if allow_none else 2):
        value = _ask(llm, grid_img, query, allow_none, zoomed)
        if value:
            return value
        if value == 0:
            return 0       # the model said "nothing to point at"
    return None


def _save(debug_dir, name, img):
    if debug_dir is None:
        return
    try:
        debug_dir.mkdir(exist_ok=True)
        img.save(debug_dir / name, quality=88)
    except Exception:
        pass


def _fit(img: Image.Image, longest: int) -> Image.Image:
    scale = longest / max(img.size)
    return img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                      Image.Resampling.LANCZOS)


def _mark_target(img: Image.Image, spot) -> Image.Image:
    """Debug picture: the screenshot with a red ring where the model pointed."""
    out = img.convert("RGB")
    d = ImageDraw.Draw(out)
    x, y = spot[0] * out.width, spot[1] * out.height
    r = max(14, out.width // 60)
    d.ellipse([x - r, y - r, x + r, y + r], outline=(255, 0, 0), width=max(3, r // 4))
    d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(255, 0, 0))
    return out


def _locate_native(llm, screenshot, query, debug_dir, allow_none):
    """Models with real grounding (Gemini): ask once for the element's box, no grid needed."""
    spot = None
    for attempt in range(1 if allow_none else 2):       # if it must exist, one retry
        try:
            spot = llm.point(screenshot, query, allow_none)
        except Exception as exc:                         # show the real reason (quota, key, network)
            print(f"[locator] {getattr(llm, 'name', 'model')} pointing failed: {exc}")
            spot = None
        if spot:
            break
    print(f"[locator] native pointing: {spot}")
    if spot:
        _save(debug_dir, "pointer_result.jpg", _mark_target(screenshot, spot))
    return spot


def locate(llm, screenshot: Image.Image, query: str, debug_dir=None,
           allow_none=True, stages: Optional[int] = None) -> Optional[Tuple[float, float]]:
    """Returns (fx, fy) as fractions of the screenshot, or None if nothing to point at."""
    if getattr(llm, "native_pointing", False):
        return _locate_native(llm, screenshot, query, debug_dir, allow_none)
    stages = stages or config.LOCATOR_STAGES
    img = screenshot.convert("RGB")
    W, H = img.size
    x0, y0, x1, y1 = 0.0, 0.0, 1.0, 1.0      # current region, as fractions of the screen
    best = None

    for stage in range(stages):
        region = img.crop((round(x0 * W), round(y0 * H), round(x1 * W), round(y1 * H)))
        grid = draw_grid(_fit(region, config.LOCATOR_WIDTH))
        _save(debug_dir, f"grid_stage{stage + 1}.jpg", grid)

        pick = _pick(llm, grid, query, allow_none and stage == 0, zoomed=stage > 0)
        print(f"[locator] round {stage + 1}/{stages}: cell {pick}")
        if not pick:
            break                       # stage 1 -> nothing to point at; later -> keep best so far

        row, col = divmod(pick - 1, GRID)
        w, h = x1 - x0, y1 - y0
        cw, ch = w / GRID, h / GRID
        best = (x0 + (col + 0.5) * cw, y0 + (row + 0.5) * ch)
        x0, x1 = (max(0.0, x0 + (col - PAD) * cw), min(1.0, x0 + (col + 1 + PAD) * cw))
        y0, y1 = (max(0.0, y0 + (row - PAD) * ch), min(1.0, y0 + (row + 1 + PAD) * ch))

    return best

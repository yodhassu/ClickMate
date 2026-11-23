# ClickMate

A voice-driven, screen-aware helper for Windows. Hold a hotkey, ask a question about whatever is on your screen, and Clicky **answers out loud** and **points at the thing with a blue cursor**. It never touches your mouse or keyboard.

Free to run, and you choose the brain: **Ollama** (fully local and offline) or **Google Gemini** (cloud, free API key, much better at pointing).

| Job | Tool |
|---|---|
| Listening (speech to text) | **whisper.cpp** (offline) |
| Thinking (sees the screenshot) | **Ollama** (`llava:7b` by default) **or Gemini** (`gemini-2.5-flash` by default) |
| Speaking | **Windows built-in voice** (SAPI5) |
| Pointing | Gemini: direct bounding box (1 call). Ollama: zoom-in grid locator. Drawn by a PyQt6 click-through overlay |

```
Ctrl+Alt+Space held -> mic records
released            -> screenshot is taken immediately
                       whisper.cpp -> text
                       Ollama or Gemini (screenshot + text) -> answer streams in
                           each finished sentence -> Windows TTS (speaks while still generating)
                       locator (Gemini box, or Ollama grid) -> where to point
                       blue cursor appears on screen for a few seconds
```

## Setup (Windows 10/11)

1. **Python 3.10+** from python.org (tick "Add to PATH").
2. **Ollama** from https://ollama.com/download, then pull a vision model:
   ```
   ollama pull llava:7b
   ```
   (Better pointing, heavier: `llama3.2-vision` or `qwen2.5vl:7b`. Set `CLICKY_MODEL` to use one.)
3. **whisper.cpp**: in PowerShell, inside this folder:
   ```
   powershell -ExecutionPolicy Bypass -File .\setup_whisper.ps1
   ```
   This downloads the prebuilt `whisper-cli.exe` and the `ggml-base.en.bin` model into `.\whisper`.
   If the script fails, download `whisper-bin-x64.zip` from the whisper.cpp releases page by hand, put the
   files in `.\whisper`, and put the model in `.\whisper\models`.
4. Double-click **`run.bat`**. First run creates a virtual environment and installs the packages.

A small blue arrow follows your mouse cursor. While you hold the hotkey it pulses red (mic is open). The question and the answer appear in a panel at the bottom of the screen as the model writes them, and the arrow flies to the thing you asked about, pulses, then returns to your cursor.

Hold **Ctrl+Alt+Space**, ask something like *"where is the save button?"* or *"what does this error mean?"*, release.
Quit from the blue icon in the system tray.

## Choosing Ollama or Gemini

**Option A: Gemini (recommended for demos; accurate pointing, no GPU needed)**
1. Get a free key (no credit card) at https://aistudio.google.com/apikey
2. Copy `.env.example` to `.env` and set:
   ```
   CLICKY_PROVIDER=gemini
   GEMINI_API_KEY=your-key-here
   ```
3. Run the app. The console should print `AI provider: Gemini (gemini-2.5-flash)`.

**Option B: Ollama (offline, private)**: skip the key, leave `CLICKY_PROVIDER` unset (or `ollama`) and follow step 2 of the setup above.

**Switch while running:** right-click the blue tray icon and pick *AI: Ollama* or *AI: Gemini*. The choice is remembered in `settings.json`. (`CLICKY_PROVIDER` in `.env` or the environment overrides the remembered choice at startup.)

Notes for Gemini:
- Your screenshot, question and answer are sent to Google. Do not demo it on a screen with private content. Free-tier data may be used by Google to improve its products.
- The free tier has daily and per-minute request limits that Google changes from time to time (check the rate limits page in AI Studio). Each question costs about 2 requests (answer + pointing). If you hit the limit you will see a "quota reached" message; switch to Ollama from the tray.
- If the default model is unavailable for your key, set `CLICKY_GEMINI_MODEL` to one listed in AI Studio.
- Never put the key in the source code or share your `.env` (it is already in `.gitignore`).

## Running from VS Code

1. Install the **Python** extension, then **File > Open Folder** and pick the folder that contains `app.py`.
2. `Ctrl+Shift+P` > **Python: Select Interpreter** > choose `.venv` (created by `run.bat`). Or make it yourself in the VS Code terminal:
   ```
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
   (If PowerShell blocks the activate script: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.)
3. Press **F5** (the "Clicky Mini" launch config is included in `.vscode/`), or run `python app.py` in the terminal.
4. Stop it with the red square in the debug bar or **Quit** in the tray icon. The terminal prints `[locator]` lines that show how pointing decided.

## Configuration

Set as environment variables or in the `.env` file (real environment variables win over `.env`). Everything is optional except the Gemini key when using Gemini:

| Variable | Default | Meaning |
|---|---|---|
| `CLICKY_PROVIDER` | `ollama` | `ollama` or `gemini` (also switchable from the tray menu) |
| `GEMINI_API_KEY` | (none) | Your free Google AI Studio key; put it in `.env` |
| `CLICKY_GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model to use |
| `CLICKY_MODEL` | `llava:7b` | Ollama vision model |
| `CLICKY_OLLAMA_HOST` | `http://localhost:11434` | Ollama address |
| `CLICKY_LANG` | `en` | Whisper language (`auto` with the multilingual `ggml-base.bin`) |
| `CLICKY_WHISPER_MODEL` | `whisper/models/ggml-base.en.bin` | Try `ggml-tiny.en.bin` for speed, `ggml-small.en.bin` for accuracy |
| `CLICKY_TTS_RATE` | `0` | Speech speed, -10 to 10 |
| `CLICKY_LOCATOR_STAGES` | `3` | Zoom rounds when pointing |
| `CLICKY_LOCATOR_WIDTH` | `768` | Image size per round; use 1280 with larger models like qwen2.5vl |
| `CLICKY_HISTORY` | `0` | Earlier Q&A pairs sent to the model. Keep at 0 with llava: it otherwise repeats old answers instead of looking at the new screen |

## Files

| File | Purpose |
|---|---|
| `app.py` | Wires everything together; the pipeline lives here |
| `hotkey.py` | Hold-to-talk hotkey (observe-only, other apps still get the keys) |
| `audio.py` | Microphone recording to 16 kHz WAV |
| `stt.py` | Runs `whisper-cli.exe` on the recording |
| `llm.py` | Ollama HTTP client (streaming chat + one-shot image questions) |
| `gemini_client.py` | Gemini HTTP client: streaming chat + native pointing (bounding box) |
| `providers.py` | Chooses Ollama or Gemini from the config |
| `locator.py` | Finds where to point: Gemini box, or the Ollama zoom-grid (see below) |
| `overlay.py` | Cursor-following blue companion + answer text panel (click-through) |
| `tts.py` | Windows SAPI5 speech with a sentence queue |
| `capture.py` | Screenshot of the primary monitor |
| `textutil.py` | Sentence splitting and text cleaning |
| `tests/` | Unit tests for the pure logic (`pytest`) |

## How pointing works (good for your report)

**With Gemini**, pointing is one call: the model is trained for visual grounding, so we ask for the target's bounding box `[ymin, xmin, ymax, xmax]` on a 0-1000 scale. The centre of the box, as fractions of the screenshot, is where the arrow flies. `debug/pointer_result.jpg` shows the screenshot with a red ring where it pointed.

**With Ollama**, small local vision models cannot output reliable pixel coordinates, and they cannot read dozens of tiny grid numbers either. They are good at picking one of nine big labelled cells, so Clicky plays "hot and cold":
1. Show the whole screen split into a **3x3 grid** (cells 1-9); the model picks the cell holding the thing.
2. **Zoom into that cell** (plus a little padding), draw a new 3x3 grid, pick again.
3. Zoom once more and pick again. The centre of the last cell is the target (about +-25 px on a 1920 px screen).

`CLICKY_LOCATOR_STAGES` sets the number of rounds (default 3; 4 is more precise but slower). If the model answers `0` in round 1, the question was conceptual and nothing is pointed at.

For questions that sound like "where / which / click / open ...", Clicky points first, so the blue cursor is already flying over while the answer is still being written. `debug/grid_stage1.jpg`, `grid_stage2.jpg`, `grid_stage3.jpg` show exactly what the model was asked to choose from in each round.

## Debugging

**Pointing doesn't work? Test the two halves separately** (no voice needed):

```
python point_test.py --ui
```
The blue arrow flies to the centre and the four corners of your screen, and the panel names where it should be (TOP-RIGHT etc.). If the label and the arrow agree, the overlay is fine.

```
python point_test.py "where is the start button"
```
You get 4 seconds to switch to the window you want analysed. It prints what the model picked and saves `debug/grid_stage1.jpg` (and stage 2, 3) so you can see the grids it chose from. If the arrow flies but lands in the wrong place, the model is the weak link: try Gemini, or `llama3.2-vision` / `qwen2.5vl:7b` on Ollama. The script uses whichever provider is configured.

- `debug/last_screenshot.jpg` is the exact image sent to the model for your last question. If an answer seems to describe the wrong screen, open it.

## Known limits

- Primary monitor only.
- Gemini needs internet and is subject to the free-tier limits; Ollama is unlimited but its pointing is weaker.
- Pointing is approximate with small local models; it is fine for buttons and menus, worse for dense toolbars.
- First answer after launch is slower while Ollama loads the model.
- English by default; switch to a multilingual Whisper model for other languages.
- Windows only (SAPI voice, overlay flags, hotkey behaviour).

## Ideas to extend it (for marks)

- Per-app memory file and a "knowledge folder" of Markdown docs injected into the prompt (the original project does this).
- Multi-monitor support.
- A settings window for model, voice and hotkey.
- Benchmark pointing accuracy across `llava`, `qwen2.5vl` and Gemini (the debug images make this easy).
- Automatic fallback to Ollama when the Gemini quota runs out.

## Credits and license

MIT. This is a simplified rewrite inspired by
[AbhishekVulla/clicky-windows](https://github.com/AbhishekVulla/clicky-windows), which is itself a Windows port of
[farzaa/clicky](https://github.com/farzaa/clicky); the grid-locator idea comes from
[Bitshank-2338/clicky-windows](https://github.com/Bitshank-2338/clicky-windows). Keep the original LICENSE and
credit them in your report.

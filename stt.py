"""Speech-to-text using the whisper.cpp command-line program (fully offline)."""
import os
import subprocess

import config
from textutil import clean_transcript


def check_installed():
    """Returns a list of problems (empty list = all good)."""
    problems = []
    if not config.WHISPER_EXE.exists():
        problems.append(f"whisper.cpp not found at {config.WHISPER_EXE} - run setup_whisper.ps1")
    if not config.WHISPER_MODEL.exists():
        problems.append(f"Whisper model not found at {config.WHISPER_MODEL} - run setup_whisper.ps1")
    return problems


def transcribe(wav_path: str) -> str:
    cmd = [
        str(config.WHISPER_EXE),
        "-m", str(config.WHISPER_MODEL),
        "-f", wav_path,
        "-l", config.WHISPER_LANG,
        "-t", str(config.WHISPER_THREADS),
        "-nt",   # no timestamps
        "-np",   # no extra prints: stdout is just the transcript
    ]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=90, creationflags=flags,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"whisper.cpp failed: {proc.stderr.strip()[:200]}")
    return clean_transcript(proc.stdout)

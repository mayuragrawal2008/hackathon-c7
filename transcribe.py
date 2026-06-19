#!/usr/bin/env python3
"""Transcribe an audio file via Groq Whisper (whisper-large-v3).

Usage:
    .venv/bin/python transcribe.py <audio_file> [output.txt]

Reads GROQ_API_KEY from .env (KEY=VALUE lines) or the environment.
"""
import os
import sys
from pathlib import Path


def load_env(path=".env"):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main():
    if len(sys.argv) < 2:
        print("usage: transcribe.py <audio_file> [output.txt]")
        sys.exit(1)

    load_env()
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        print("ERROR: GROQ_API_KEY not found. Put it in .env as GROQ_API_KEY=...")
        sys.exit(1)

    audio_path = Path(sys.argv[1])
    if not audio_path.exists():
        print(f"ERROR: audio file not found: {audio_path}")
        sys.exit(1)

    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else audio_path.with_suffix(".txt")

    from groq import Groq

    client = Groq(api_key=key)
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            file=(audio_path.name, f.read()),
            model="whisper-large-v3",
            response_format="text",
        )

    text = result if isinstance(result, str) else getattr(result, "text", str(result))
    out_path.write_text(text)
    print(f"Transcript written to {out_path}\n")
    print(text)


if __name__ == "__main__":
    main()

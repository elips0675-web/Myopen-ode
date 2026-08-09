"""Stage 43: optional Whisper speech-to-text (offline).

Browser Web Speech API (stage 34) works in Chrome/Edge, but not everywhere
(Firefox, some Android WebViews). This module adds a server-side fallback:

- AI_STT_URL=https://host:port   -> proxy to a running Whisper server
  (whisper.cpp server, faster-whisper, WhisperX...). The remote must accept
  multipart/form-data with field 'file' and return JSON {"text": "..."}.
- AI_STT_BINARY=C:\\whisper\\main.exe -> run a local whisper.cpp binary:
    main.exe -m ggml-base.bin -f <audio> -np 1 -nt 1 -l ru -otxt
  Reads the produced .txt file next to the audio.
- Neither set -> POST /api/stt returns 501 with a hint (browser STT used).

Only invoked when the UI explicitly sends audio (no SpeechRecognition API).
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File

router = APIRouter()

_EXT_OK = {".wav", ".mp3", ".ogg", ".m4a", ".webm"}


def transcribe(audio_path: str):
    """Transcribe a local audio file via configured backend."""
    url = os.environ.get("AI_STT_URL", "").strip()
    if url:
        return _via_url(url, audio_path)
    binary = os.environ.get("AI_STT_BINARY", "").strip()
    if binary:
        return _via_binary(binary, audio_path)
    raise HTTPException(status_code=501, detail="No STT backend: set AI_STT_URL or AI_STT_BINARY")


def _via_url(url, audio_path):
    import requests
    with open(audio_path, "rb") as f:
        r = requests.post(url.rstrip("/") + "/inference",
                          files={"file": (Path(audio_path).name, f)}, timeout=120)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        return data.get("text") or data.get("transcript") or data.get("result") or ""
    return str(data)


def _via_binary(binary, audio_path):
    out_txt = Path(audio_path).with_suffix(".txt")
    cmd = [binary, "-m", os.environ.get("AI_STT_MODEL", "ggml-base.bin"),
           "-f", audio_path, "-np", "1", "-nt", "1",
           "-l", os.environ.get("AI_STT_LANG", "ru"), "-otxt"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if out_txt.exists():
        text = out_txt.read_text("utf-8", errors="ignore").strip()
        out_txt.unlink(missing_ok=True)
        return text
    raise HTTPException(status_code=500, detail="Whisper produced no output: " + (r.stderr or r.stdout)[-300:])


@router.post("/api/stt")
async def stt_upload(file: UploadFile = File(...)):
    name = (file.filename or "voice.webm").lower()
    ext = Path(name).suffix
    if ext not in _EXT_OK:
        raise HTTPException(status_code=400, detail=f"Unsupported audio type '{ext}', allowed: {sorted(_EXT_OK)}")
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Audio too large (max 25 MB)")
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio")
    tmp = Path(tempfile.gettempdir()) / f"stt_{os.getpid()}_{name}"
    try:
        tmp.write_bytes(data)
        text = transcribe(str(tmp))
        return {"text": text}
    finally:
        tmp.unlink(missing_ok=True)


@router.get("/api/stt/status")
def stt_status():
    return {
        "url": bool(os.environ.get("AI_STT_URL", "").strip()),
        "binary": bool(os.environ.get("AI_STT_BINARY", "").strip()),
        "browser_stt": "available",
    }

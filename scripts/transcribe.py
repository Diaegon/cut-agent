"""Transcreve work/<id>/video.mp4 com timestamps por palavra.

Uso: uv run scripts/transcribe.py <work_dir> [--model small] [--language pt]

Gera:
  transcript.json  segmentos + palavras (usado pelo render para legendas e snapping)
  transcript.txt   versão compacta "[mm:ss.s] texto" para o LLM ler
"""
import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel


def fmt(t: float) -> str:
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:04.1f}"


def load_audio(video: Path) -> np.ndarray:
    """Decodifica para mono 16 kHz float32 via ffmpeg (evita depender do PyAV)."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def run(model: WhisperModel, audio: np.ndarray, language: str | None):
    segments, info = model.transcribe(
        audio, language=language, word_timestamps=True, vad_filter=True
    )
    segs = []
    for seg in segments:  # gerador: a inferência acontece aqui
        words = [
            {"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)}
            for w in (seg.words or [])
            if w.word.strip()
        ]
        segs.append({"s": round(seg.start, 2), "e": round(seg.end, 2), "text": seg.text.strip(), "words": words})
    return segs, info.language


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--model", default="small", help="tiny, base, small, medium, large-v3")
    ap.add_argument("--language", default=None, help="ex.: pt, en (padrão: detectar)")
    ap.add_argument("--cpu", action="store_true", help="forçar CPU")
    args = ap.parse_args()

    work = Path(args.work_dir)
    out_json = work / "transcript.json"
    if out_json.exists():
        print(f"já existe: {out_json}")
        return
    audio = load_audio(work / "video.mp4")

    segs = lang = None
    if not args.cpu:
        try:
            segs, lang = run(WhisperModel(args.model, device="cuda", compute_type="float16"), audio, args.language)
        except Exception as e:  # sem CUDA/cuDNN ou VRAM insuficiente
            print(f"GPU falhou ({e.__class__.__name__}: {e}); usando CPU int8")
    if segs is None:
        segs, lang = run(WhisperModel(args.model, device="cpu", compute_type="int8"), audio, args.language)

    out_json.write_text(json.dumps({"language": lang, "segments": segs}, ensure_ascii=False))
    (work / "transcript.txt").write_text("\n".join(f"[{fmt(s['s'])}] {s['text']}" for s in segs))
    print(f"idioma: {lang} | segmentos: {len(segs)} | {work / 'transcript.txt'}")


if __name__ == "__main__":
    main()

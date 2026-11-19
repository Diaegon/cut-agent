"""Baixa um vídeo do YouTube para work/<video_id>/.

Uso: uv run scripts/download.py <url> [--work-root work]
Imprime o caminho do diretório de trabalho na última linha.
"""
import argparse
import json
from pathlib import Path

import yt_dlp


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--work-root", default="work")
    args = ap.parse_args()

    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(args.url, download=False)

    work = Path(args.work_root) / info["id"]
    work.mkdir(parents=True, exist_ok=True)
    video = work / "video.mp4"

    if not video.exists():
        opts = {
            # Até 1080p já sobra resolução para recortar 9:16.
            "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/b",
            "merge_output_format": "mp4",
            "outtmpl": str(video),
            "quiet": True,
            "noprogress": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([args.url])

    meta = {
        "id": info["id"],
        "url": args.url,
        "title": info.get("title"),
        "channel": info.get("channel"),
        "duration": info.get("duration"),
        "license": info.get("license"),
        "chapters": info.get("chapters") or [],
    }
    (work / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"título: {meta['title']} | canal: {meta['channel']} | licença: {meta['license']}")
    print(work)


if __name__ == "__main__":
    main()

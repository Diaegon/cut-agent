"""Renderiza os cortes de work/<id>/clips.json como Shorts 1080x1920.

Uso: uv run scripts/render.py <work_dir> [--only 2] [--no-captions] [--font "DejaVu Sans"]

Para cada corte:
  1. ajusta início/fim para limites de palavra (não corta no meio da fala);
  2. detecta o rosto do palestrante e calcula um enquadramento 9:16 suavizado;
  3. gera legenda .ass estilo "palavra ativa destacada";
  4. codifica com ffmpeg (H.264 + AAC).
Saída: work/<id>/out/clip_XX.mp4 e work/<id>/out/posts.md
"""
import argparse
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

OUT_W, OUT_H = 1080, 1920
DETECT_FPS = 4
SMOOTH_SECONDS = 1.5


# ---------------------------------------------------------------- utilidades

def probe(video: Path) -> tuple[int, int, str]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate", "-of", "json", str(video)],
        capture_output=True, text=True, check=True,
    ).stdout
    s = json.loads(out)["streams"][0]
    return s["width"], s["height"], s["r_frame_rate"]


def flat_words(transcript: dict) -> list[dict]:
    return [w for seg in transcript["segments"] for w in seg["words"]]


def snap(start: float, end: float, words: list[dict]) -> tuple[float, float]:
    """Move início para o começo da palavra mais próxima e fim para o fim da palavra mais próxima."""
    if not words:
        return start, end
    s = min(words, key=lambda w: abs(w["s"] - start))["s"]
    e = min(words, key=lambda w: abs(w["e"] - end))["e"]
    return max(0.0, s - 0.08), e + 0.25


# ---------------------------------------------------------- enquadramento 9:16

def face_track(video: Path, start: float, end: float, W: int, H: int) -> tuple[np.ndarray, np.ndarray]:
    """Retorna (tempos, centro_x normalizado) do maior rosto, amostrado a DETECT_FPS."""
    sw = 640
    sh = int(round(sw * H / W / 2)) * 2
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-ss", f"{start}", "-to", f"{end}", "-i", str(video),
         "-vf", f"fps={DETECT_FPS},scale={sw}:{sh}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        stdout=subprocess.PIPE,
    )
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    ts, xs = [], []
    i = 0
    while True:
        buf = proc.stdout.read(sw * sh)
        if len(buf) < sw * sh:
            break
        frame = np.frombuffer(buf, np.uint8).reshape(sh, sw)
        faces = cascade.detectMultiScale(frame, scaleFactor=1.1, minNeighbors=6, minSize=(sh // 12, sh // 12))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            ts.append(i / DETECT_FPS)
            xs.append((x + w / 2) / sw)
        i += 1
    proc.wait()
    return np.array(ts), np.array(xs)


def crop_positions(ts, xs, n_frames: int, fps: float, W: int, cw: int) -> np.ndarray:
    """Posição x (px) do recorte para cada frame, suavizada."""
    if len(xs) == 0:
        return np.full(n_frames, (W - cw) // 2, dtype=int)
    t_frames = np.arange(n_frames) / fps
    cx = np.interp(t_frames, ts, xs)  # preenche lacunas segurando/interpolando
    k = max(1, int(SMOOTH_SECONDS * fps))
    kernel = np.ones(k) / k
    cx = np.convolve(np.pad(cx, (k // 2, k - 1 - k // 2), mode="edge"), kernel, mode="valid")
    x = np.clip(cx * W - cw / 2, 0, W - cw)
    return x.astype(int)


# ------------------------------------------------------------------ legendas

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,7,2,2,60,60,520,1
Style: Title,{font},64,&H00FFFFFF,&H00FFFFFF,&H00000000,&HC0000000,1,0,0,0,100,100,0,0,3,18,0,8,70,70,170,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
HIGHLIGHT = r"{\c&H00E5FF&}"  # amarelo (BGR)
RESET = r"{\c&HFFFFFF&}"


def ass_time(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def ass_escape(s: str) -> str:
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def chunk_words(words: list[dict], max_words: int = 3, gap: float = 0.45) -> list[list[dict]]:
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["s"] - cur[-1]["e"] > gap or cur[-1]["w"][-1] in ".?!,;:"):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(words: list[dict], start: float, end: float, title: str | None, font: str) -> str:
    lines = [ASS_HEADER.format(w=OUT_W, h=OUT_H, font=font)]
    if title:
        lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(end - start)},Title,,0,0,0,,{ass_escape(title)}")
    clip_words = [w for w in words if w["s"] >= start - 0.05 and w["e"] <= end + 0.05]
    for chunk in chunk_words(clip_words):
        texts = [ass_escape(w["w"]).upper() for w in chunk]
        for i, w in enumerate(chunk):
            s = w["s"] - start
            e = (chunk[i + 1]["s"] if i + 1 < len(chunk) else w["e"]) - start
            parts = [f"{HIGHLIGHT}{t}{RESET}" if j == i else t for j, t in enumerate(texts)]
            lines.append(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Cap,,0,0,0,,{' '.join(parts)}")
    return "\n".join(lines) + "\n"


# -------------------------------------------------------------------- render

def render_clip(video: Path, W: int, H: int, fps_str: str, start: float, end: float,
                ass_path: Path | None, out: Path) -> None:
    num, den = (int(x) for x in fps_str.split("/"))
    fps = num / den
    n_frames = int(round((end - start) * fps))
    cw = min(W, int(round(H * 9 / 16 / 2)) * 2)

    ts, xs = face_track(video, start, end, W, H)
    xpos = crop_positions(ts, xs, n_frames, fps, W, cw)
    print(f"  rostos detectados em {len(xs)} amostras")

    vf = f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,pad={OUT_W}:{OUT_H}:-1:-1,setsar=1"
    if ass_path:
        vf += f",ass={ass_path}"

    dec = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-ss", f"{start}", "-to", f"{end}", "-i", str(video),
         "-an", "-r", fps_str, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE,
    )
    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{cw}x{H}", "-r", fps_str, "-i", "-",
         "-ss", f"{start}", "-to", f"{end}", "-i", str(video),
         "-map", "0:v", "-map", "1:a?", "-vf", vf,
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE,
    )
    frame_bytes = W * H * 3
    i = 0
    while True:
        buf = dec.stdout.read(frame_bytes)
        if len(buf) < frame_bytes:
            break
        frame = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        x = xpos[min(i, len(xpos) - 1)]
        enc.stdin.write(np.ascontiguousarray(frame[:, x:x + cw]).tobytes())
        i += 1
    dec.wait()
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError(f"ffmpeg falhou em {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--clips", default=None, help="padrão: <work_dir>/clips.json")
    ap.add_argument("--only", type=int, default=None, help="renderiza só o corte com este id")
    ap.add_argument("--no-captions", action="store_true")
    ap.add_argument("--no-title", action="store_true")
    ap.add_argument("--font", default="Montserrat")
    args = ap.parse_args()

    work = Path(args.work_dir)
    video = work / "video.mp4"
    clips = json.loads(Path(args.clips or work / "clips.json").read_text())
    words = flat_words(json.loads((work / "transcript.json").read_text()))
    W, H, fps_str = probe(video)
    out_dir = work / "out"
    out_dir.mkdir(exist_ok=True)

    posts = []
    for c in clips:
        if args.only is not None and c["id"] != args.only:
            continue
        start, end = snap(float(c["start"]), float(c["end"]), words)
        dur = end - start
        name = f"clip_{c['id']:02d}"
        print(f"[{name}] {start:.2f}-{end:.2f} ({dur:.1f}s) {c.get('title', '')}")
        if not 10 <= dur <= 90:
            print(f"  aviso: duração {dur:.1f}s fora do intervalo recomendado (20-60s)")

        ass_path = None
        if not args.no_captions:
            ass_path = out_dir / f"{name}.ass"
            title = None if args.no_title else c.get("title")
            ass_path.write_text(build_ass(words, start, end, title, args.font))

        render_clip(video, W, H, fps_str, start, end, ass_path, out_dir / f"{name}.mp4")
        posts.append(
            f"## {name}.mp4 — score {c.get('score', '?')}\n\n"
            f"**Título:** {c.get('title', '')}\n\n"
            f"**Gancho:** {c.get('hook', '')}\n\n"
            f"**Descrição:** {c.get('description', '')}\n\n"
            f"**Hashtags:** {' '.join(c.get('hashtags', []))}\n\n"
            f"**Por quê:** {c.get('reason', '')}\n"
        )

    if args.only is None:
        (out_dir / "posts.md").write_text("\n".join(posts))
    print(f"pronto: {out_dir}")


if __name__ == "__main__":
    main()

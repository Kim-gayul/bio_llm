"""Render BioLab's 30-second original motion graphic with Pillow + FFmpeg.

No network calls, external stock footage, or third-party music.
Usage: python promo/render.py [--preview]
"""
import argparse
import math
import subprocess
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "promo" / "output"
W, H, FPS, DURATION = 1920, 1080, 30, 30
INK = "#162d28"
GREEN = "#347d66"
MINT = "#bce9c5"
CREAM = "#f5f6ee"
WHITE = "#ffffff"
MUTED = "#859d90"
FONT = Path("C:/Windows/Fonts/malgun.ttf")
BOLD = Path("C:/Windows/Fonts/malgunbd.ttf")
LATIN = Path("C:/Windows/Fonts/segoeui.ttf")
LATIN_BOLD = Path("C:/Windows/Fonts/segoeuib.ttf")
SCENES = [(0, 4), (4, 8), (8, 15), (15, 20.5), (20.5, 25), (25, 30)]


def ease(x):
    x = max(0, min(1, x))
    return 1 - (1 - x) ** 3


@lru_cache(maxsize=128)
def font(size, bold=False, latin=False):
    return ImageFont.truetype(str((LATIN_BOLD if bold else LATIN) if latin else (BOLD if bold else FONT)), size)


@lru_cache(maxsize=1000)
def lettering(text, size, color, bold=False, latin=False):
    f = font(size, bold, latin)
    box = f.getbbox(text)
    im = Image.new("RGBA", (max(1, box[2] + 6), size * 2), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((0, -box[1] + 2), text, font=f, fill=color)
    return im.crop((0, 0, im.width, box[3] - box[1] + 5))


def text(im, value, xy, size=30, color=INK, bold=False, latin=False, alpha=1):
    layer = lettering(value, size, color, bold, latin)
    if alpha < 1:
        layer = layer.copy()
        layer.putalpha(layer.getchannel("A").point(lambda a: int(a * max(0, alpha))))
    im.paste(layer, (int(xy[0]), int(xy[1])), layer)


def wrapped(im, value, xy, width, size, color=INK, bold=False, max_lines=3):
    words = value.split()
    lines, line = [], ""
    f = font(size, bold)
    for word in words:
        candidate = (line + " " + word).strip()
        if f.getlength(candidate) > width and line:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,") + "…"
    for i, line in enumerate(lines):
        text(im, line, (xy[0], xy[1] + i * size * 1.55), size, color, bold)


def roundrect(im, box, fill, radius=22, outline=None, width=1):
    ImageDraw.Draw(im).rounded_rectangle(tuple(int(v) for v in box), radius, fill=fill, outline=outline, width=width)


def line(im, points, color, width=2):
    ImageDraw.Draw(im).line(points, fill=color, width=width)


def pill(im, label, xy, fill, color, size=23):
    width = font(size).getlength(label) + 40
    roundrect(im, (xy[0], xy[1], xy[0] + width, xy[1] + 48), fill, 24)
    text(im, label, (xy[0] + 20, xy[1] + 10), size, color)
    return width


def dna(im, cx, cy, height, phase=0, color=MINT):
    d = ImageDraw.Draw(im)
    a, b = [], []
    for i in range(161):
        y = cy - height / 2 + height * i / 160
        x = math.sin(i / 160 * math.pi * 3 + phase) * height * .23
        a.append((int(cx + x), int(y)))
        b.append((int(cx - x), int(y)))
        if i % 13 == 0:
            d.line((a[-1], b[-1]), fill=color, width=max(2, int(height / 95)))
    d.line(a, fill=color, width=max(3, int(height / 48)))
    d.line(b, fill=color, width=max(3, int(height / 48)))


@lru_cache(maxsize=2)
def background(dark=True):
    y, x = np.mgrid[0:H, 0:W]
    glow = np.exp(-(((x - 1490) / 900) ** 2 + ((y - 500) / 750) ** 2))
    base = np.array([15, 38, 32] if dark else [245, 246, 238])
    light = np.array([24, 36, 21] if dark else [-10, -5, -10])
    rgb = np.clip(base[None, None, :] + glow[:, :, None] * light, 0, 255).astype("uint8")
    return Image.fromarray(rgb)


def brand(im, dark=True, small=False):
    color = CREAM if dark else INK
    dna(im, 109, 94, 43, .2, MINT if dark else GREEN)
    text(im, "BioLab", (149, 72), 41, color, True, True)
    if not small:
        text(im, "나의 첫 연구 파트너", (325, 86), 22, MUTED)


def footer(im, number, dark=True):
    color = "#759483" if dark else "#8d9e91"
    text(im, "MOLECULAR BIOLOGY / RESEARCH COMPANION", (94, 1008), 17, color, latin=True)
    text(im, f"0{number + 1} / 06", (1714, 1008), 20, color, latin=True)


def dots(im, t, dark=True):
    d = ImageDraw.Draw(im)
    color = "#315542" if dark else "#dce4d5"
    for i in range(17):
        x = 1000 + (i * 83) % 830
        y = 195 + ((i * 97 + t * (8 + i % 4)) % 710)
        r = 2 + i % 3
        d.ellipse((x-r, y-r, x+r, y+r), fill=color)


def headline(im, lines, xy, t, size=88, dark=True):
    for i, value in enumerate(lines):
        p = ease((t - .12 * i) / .8)
        text(im, value, (xy[0], xy[1] + i * size * 1.42 + 28 * (1-p)), size,
             MINT if dark and i == len(lines)-1 else CREAM if dark else INK, True, alpha=p)


# Illustrative content only. No third-party article text is bundled or rendered.
PAPERS = [{"pmcid": "PMC 예시", "title": "논문 제목과 출처를 확인하세요",
           "methods_chunks": [{"text": "Materials & Methods에서는 연구에 사용한 시료, 절차와 조건을 확인할 수 있습니다. 질문에 적용하기 전에 원문과 연구실의 SOP를 함께 살펴보세요."}]}]


def scene0(t):
    im = background().copy()
    dots(im, t)
    brand(im)
    text(im, "FOR YOUR FIRST SEMESTER", (100, 255), 24, MUTED, latin=True)
    headline(im, ["첫 연구,", "혼자 시작하지 마세요."], (94, 336), t, 96)
    text(im, "낯선 논문. 복잡한 Methods. 끝없는 질문.", (100, 662), 32, "#b1c0b2", alpha=ease((t-.5)/.8))
    dna(im, 1500, 520, 390, t * .45, "#74b78b")
    d = ImageDraw.Draw(im)
    d.ellipse((1240, 260, 1760, 780), outline="#365d48", width=2)
    d.arc((1185, 205, 1815, 835), int(t*14), int(t*14+235), fill="#577d5c", width=2)
    pill(im, "석사 신입생을 위한 연구 공간", (100, 809), "#294b3b", "#cae0cb")
    footer(im, 0)
    return im


def scene1(t):
    im = background().copy()
    brand(im)
    dots(im, t)
    text(im, "MEET YOUR RESEARCH PARTNER", (100, 225), 24, MUTED, latin=True)
    p = ease(t/.85)
    text(im, "BioLab.", (88, 316 + 30*(1-p)), 177, CREAM, True, True, p)
    headline(im, ["논문을 함께 읽는", "나의 AI 사수 선배"], (103, 567), t-.25, 57)
    roundrect(im, (1160, 230, 1760, 825), "#264a3a", 44, "#497257", 2)
    dna(im, 1460, 415, 178, t*.45, MINT)
    text(im, "질문은 편하게", (1270, 580), 41, CREAM, True)
    text(im, "설명은 한국어로", (1230, 653), 41, MINT, True)
    pill(im, "PMC 논문 기반", (1320, 739), "#355b43", "#d4e7cf", 21)
    footer(im, 1)
    return im


def window_shell(im, box):
    x1, y1, x2, y2 = box
    roundrect(im, (x1+10,y1+17,x2+10,y2+17), "#dce3d6", 26)
    roundrect(im, box, WHITE, 24, "#dbe4d8", 2)
    d = ImageDraw.Draw(im)
    for i, c in enumerate(["#d6a69a", "#dec995", "#a8c29a"]):
        d.ellipse((x1+26+i*22,y1+23,x1+36+i*22,y1+33), fill=c)
    text(im, "BioLab / Research workspace", (x1+115,y1+18), 18, "#94a18e", latin=True)
    line(im, [(x1,y1+57),(x2,y1+57)], "#e8ede3")


def scene2(t):
    im = background(False).copy()
    brand(im, False)
    text(im, "01 / ASK IN YOUR OWN WORDS", (98, 238), 22, GREEN, latin=True)
    headline(im, ["궁금한 순간,", "한국어로 물어보세요."], (94, 345), t, 65, False)
    text(im, "질문부터 후속 대화까지", (100, 593), 32, "#75846b")
    text(im, "이전 맥락을 이어가는 연구 대화.", (100, 646), 29, "#75846b")
    pill(im, "실시간 답변", (100, 778), "#e0ead9", GREEN)
    pill(im, "대화 저장", (296, 778), "#e0ead9", GREEN)
    window_shell(im, (870, 192, 1810, 894))
    roundrect(im, (902, 272, 1778, 384), "#edf2e7", 19)
    text(im, "이 논문의 Methods,", (930, 296), 29, INK)
    text(im, "어디부터 읽어야 할까요?", (930, 340), 29, INK)
    dna(im, 930, 441, 34, .2, GREEN)
    text(im, "AI 사수 선배", (963, 424), 24, GREEN, True)
    response = ["핵심 실험을 파악하고,", "Methods 원문과 출처를", "함께 확인해요."]
    for i, value in enumerate(response):
        reveal = max(0, min(len(value), int((t - 1.0 - i*.8)*17)))
        if reveal:
            text(im, value[:reveal], (930, 494 + i*55), 32, INK, True)
    if t > 3.4:
        pill(im, PAPERS[0]["pmcid"], (930, 692), "#e6f0df", GREEN, 22)
        text(im, "원문 근거 보기 →", (1190, 704), 23, GREEN)
    roundrect(im, (910, 787, 1770, 855), "#fbfcf8", 14, "#e0e8d8", 2)
    text(im, "후속 질문을 입력하세요…", (936, 808), 23, "#a1ad95")
    roundrect(im, (1692, 800, 1742, 842), GREEN, 12)
    text(im, "↑", (1706, 802), 27, WHITE)
    text(im, "기능 소개를 위한 연출 화면 · 실제 답변은 질문과 근거에 따라 달라집니다", (871, 933), 20, "#88957e")
    footer(im, 2, False)
    return im


def scene3(t):
    im = background(False).copy()
    brand(im, False)
    text(im, "02 / FOLLOW THE EVIDENCE", (98, 222), 22, GREEN, latin=True)
    headline(im, ["답변에서 끝내지 않고,", "논문의 근거까지."], (94, 313), t, 70, False)
    text(im, "PMCID 출처 · Methods 원문 · 논문 라이브러리", (100, 559), 29, "#78876c")
    for i, label in enumerate(["01  논문 찾기", "02  근거 읽기", "03  대화 내보내기"]):
        p = ease((t-.4-i*.2)/.7)
        text(im, label, (101, 674+i*76+18*(1-p)), 32, GREEN, True, alpha=p)
    x, y = 1050, 243
    roundrect(im, (x+45, y-26, 1815, 887), "#e5eadf", 24)
    roundrect(im, (x+22, y-12, 1792, 900), "#eef1e9", 24, "#d7dfce")
    roundrect(im, (x, y, 1770, 920), WHITE, 24, "#d4dfcd", 2)
    pill(im, PAPERS[0]["pmcid"], (x+38,y+34), "#e8f1e1", GREEN, 22)
    wrapped(im, PAPERS[0]["title"], (x+38,y+121), 628, 30, INK, True, 3)
    line(im, [(x+38,y+308),(1732,y+308)], "#e0e7d9", 2)
    text(im, "Materials & Methods", (x+38,y+345), 29, GREEN, True, True)
    excerpt = PAPERS[0]["methods_chunks"][0]["text"]
    wrapped(im, excerpt, (x+38,y+402), 622, 24, "#7f8f72", False, 4)
    text(im, "PMC 원문에서 확인하기  ↗", (x+38,y+604), 24, GREEN, True)
    footer(im, 3, False)
    return im


def scene4(t):
    im = background().copy()
    brand(im)
    dots(im, t)
    text(im, "03 / LOCAL AI, YOUR WORKSPACE", (100, 217), 22, MUTED, latin=True)
    headline(im, ["질문과 AI 추론은", "내 컴퓨터 안에서."], (98, 300), t, 76)
    labels = [("Next.js", "연구 화면"), ("Django", "대화와 데이터"), ("Ollama + RAG", "논문 기반 로컬 AI")]
    for i, (title, sub) in enumerate(labels):
        x = 100 + i * 580
        p = ease((t-.25-i*.14)/.7)
        dy = 20*(1-p)
        roundrect(im, (x,640+dy,x+510,828+dy), "#284b3b", 22, "#48674b", 2)
        text(im, title, (x+31,674+dy), 40, CREAM, True, True, p)
        text(im, sub, (x+31,747+dy), 27, "#acc6a8", alpha=p)
        if i < 2:
            text(im, "→", (x+525,703), 37, "#7eab7c")
    # A traveling marker makes the local request path visible without implying live inference.
    travel = (t * .28) % 1
    px = 142 + travel * 1535
    ImageDraw.Draw(im).ellipse((px-6, 844, px+6, 856), fill=MINT)
    text(im, "상용 LLM API 없이 · 기존 논문 데이터와 로컬 모델로", (104, 877), 25, "#a2bb9f")
    text(im, "최초 설치·모델 다운로드·논문 수집·외부 원문 열람에는 인터넷이 필요합니다.", (103, 940), 20, "#718f77")
    footer(im, 4)
    return im


def scene5(t):
    im = background().copy()
    brand(im)
    dots(im, t)
    text(im, "BUILD YOUR RESEARCH COMPANION", (100, 233), 23, MUTED, latin=True)
    headline(im, ["함께 만드는", "연구의 첫걸음."], (94, 329), t, 91)
    text(im, "BioLab을 오픈소스로 함께 발전시켜요.", (102, 613), 32, "#c2d5be", alpha=ease((t-.3)/.7))
    pill(im, "코드 살펴보기", (101, 725), MINT, INK, 25)
    pill(im, "아이디어 나누기", (325, 725), "#2c513c", "#cee2c7", 25)
    text(im, "GitHub에서 BioLab을 만나보세요", (102, 833), 39, CREAM, True)
    roundrect(im, (1320, 316, 1755, 750), "#284c39", 44, "#507856", 2)
    dna(im, 1540, 482, 196, t*.28, MINT)
    text(im, "BioLab.", (1408, 633), 68, CREAM, True, True)
    text(im, "배우는 연구자에서, 함께 만드는 연구자로.", (103, 943), 23, "#87a180")
    footer(im, 5)
    return im


RENDERERS = [scene0, scene1, scene2, scene3, scene4, scene5]


def frame(t):
    idx = next((i for i, (_, end) in enumerate(SCENES) if t < end), 5)
    start, _ = SCENES[idx]
    local = t-start
    im = RENDERERS[idx](local)
    if idx and local < .4:
        prev = RENDERERS[idx-1](SCENES[idx-1][1]-SCENES[idx-1][0])
        im = Image.blend(prev, im, ease(local/.4))
    # Thin playback line ties all six scenes together.
    ImageDraw.Draw(im).rectangle((0,1075,int(W*t/DURATION),1079), fill="#a7d6a8")
    return im


def make_music():
    sr = 44100
    audio = np.zeros((sr*DURATION, 2), dtype=np.float64)
    rng = np.random.default_rng(7)

    def note(start, duration, frequency, amplitude, pan=0, pad=False):
        first = int(start*sr)
        count = min(int(duration*sr), len(audio)-first)
        if count <= 0:
            return
        t = np.arange(count)/sr
        if pad:
            envelope = np.minimum(t/.6,1)*np.minimum((duration-t)/1.1,1)
            wave_data = np.sin(2*np.pi*frequency*t) + .24*np.sin(2*np.pi*frequency*2.002*t)
        else:
            envelope = (1-np.exp(-t*100))*np.exp(-t*3.8)*np.minimum((duration-t)/.1,1)
            wave_data = np.sin(2*np.pi*frequency*t) + .32*np.sin(2*np.pi*frequency*2*t) + .12*np.sin(2*np.pi*frequency*3*t)
        signal = amplitude*envelope*wave_data
        audio[first:first+count,0] += signal*math.sqrt((1-pan)/2)
        audio[first:first+count,1] += signal*math.sqrt((1+pan)/2)

    def hz(midi):
        return 440*2**((midi-69)/12)

    chords = [[57,60,64,71], [53,57,60,64], [48,55,60,64], [55,59,62,69]]
    beat = 60/96
    for block in range(12):
        start = block*2.5
        chord = chords[block % 4]
        for n, midi in enumerate(chord):
            note(start, min(3.6,DURATION-start), hz(midi-12), .028, (n-1.5)/3, True)
        for step in range(8):
            st = start + step*beat/2
            if st < 28.8:
                note(st,1.7,hz(chord[[0,2,1,3,2,1,3,2][step]]+12),.067, math.sin(step*1.4)*.48)
    for b in np.arange(4,28.5,beat):
        n = int(.2*sr)
        t = np.arange(n)/sr
        pulse = .075*np.sin(2*np.pi*(48*t+3*(1-np.exp(-t*24))))*np.exp(-t*24)
        first = int(b*sr)
        audio[first:first+n] += pulse[:,None]
    for position in [4,8,15,20.5,25]:
        count = int(.38*sr)
        tt = np.linspace(0,1,count)
        noise = rng.normal(0,1,count)
        noise = np.convolve(noise, np.ones(23)/23, mode="same")*.05*np.sin(np.pi*tt)**2
        first = int((position-.3)*sr)
        audio[first:first+count] += noise[:,None]
    envelope = np.minimum(np.arange(len(audio))/sr/1.3,1)*np.minimum((DURATION-np.arange(len(audio))/sr)/1.7,1)
    audio *= envelope[:,None]
    audio = np.tanh(audio*1.45)
    pcm = (np.clip(audio,-1,1)*32767).astype("<i2")
    path = OUT / "biolab-original-music.wav"
    with wave.open(str(path),"wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(sr)
        output.writeframes(pcm.tobytes())
    return path


def previews():
    times = [2.4,6.6,12.7,18.5,23.5,28.0]
    for i, t in enumerate(times):
        still = frame(t)
        still.save(OUT / f"scene-{i+1:02d}.jpg", quality=94)
    # A 3x2 contact sheet without overlap.
    sheet = Image.new("RGB", (1440, 810), "#e7eadf")
    for i,t in enumerate(times):
        sheet.paste(frame(t).resize((480,270),Image.Resampling.LANCZOS), ((i%3)*480,(i//3)*405+55))
        ImageDraw.Draw(sheet).text(((i%3)*480+15,(i//3)*405+338), f"{SCENES[i][0]:g}–{SCENES[i][1]:g} sec",font=font(22,latin=True),fill=INK)
    sheet.save(OUT / "biolab-storyboard.jpg", quality=95)
    frame(6.6).save(OUT / "biolab-poster.jpg", quality=96)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview",action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    previews()
    if args.preview:
        return
    music = make_music()
    path = OUT / "BioLab-promo-30s-1080p.mp4"
    cmd = ["ffmpeg","-y","-hide_banner","-loglevel","warning",
           "-f","rawvideo","-pixel_format","rgb24","-video_size",f"{W}x{H}","-framerate",str(FPS),"-i","pipe:0",
           "-i",str(music),"-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","fast","-crf","19",
           "-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-ar","48000","-af","loudnorm=I=-18:TP=-1.5:LRA=8",
           "-t",str(DURATION),"-movflags","+faststart","-metadata","title=BioLab - Your First Research Partner",
           "-metadata","comment=Original motion graphics and procedurally composed music. Illustrative UI, not a screen recording.",str(path)]
    process = subprocess.Popen(cmd,stdin=subprocess.PIPE)
    try:
        for n in range(FPS*DURATION):
            process.stdin.write(frame(n/FPS).tobytes())
            if n % 150 == 0:
                print(f"Rendered {n}/{FPS*DURATION} frames",flush=True)
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("FFmpeg render failed")
    print(f"Saved: {path}",flush=True)


if __name__ == "__main__":
    main()

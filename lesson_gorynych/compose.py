"""Captions + synthesized sound + H.264 for the «Змей Горыныч» reel.
usage: python compose.py frames_dir out_dir fonts_dir [--test]
"""
import sys, os, glob, math, wave, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FR, OUT, FONTS = sys.argv[1], sys.argv[2], sys.argv[3]
TEST = '--test' in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(OUT, exist_ok=True)
FPS, N, W, H = 30, 480, 1080, 1920
F_BUILD, STEP_DT, NSTEP = 30, 3.6, 37
F_GO, F_TURN, F_BACK, F_HOME, F_CARD = 186, 246, 306, 366, 396

def font(weight, size):
    p = os.path.join(FONTS, 'Montserrat.ttf')
    try:
        f = ImageFont.truetype(p, size)
        try: f.set_variation_by_axes([weight])
        except Exception: pass
        return f
    except Exception:
        return ImageFont.truetype('DejaVuSans-Bold.ttf', size)

INK = (15, 31, 42); GREEN = (27, 107, 92); PINK = (236, 74, 134); CREAM = (255, 255, 255)
LOGO = Image.open(os.path.join(HERE, 'logo.png')).convert('RGBA')

def ease(u): u = min(max(u, 0), 1); return 1 - (1 - u) ** 3
def pop(t, t0, t1, dur=7):
    """0..1 appear / disappear factor"""
    if t < t0 or t >= t1: return 0.0
    return min(ease((t - t0) / dur), ease((t1 - t) / dur))

def plate(img, cx, cy, lines, size, alpha, bg=CREAM, fg=INK, pad=(44, 26), radius=40, weight=800):
    if alpha <= 0.01: return
    f = font(weight, size)
    d0 = ImageDraw.Draw(img)
    ws = [d0.textlength(l, font=f) for l in lines]; lh = int(size * 1.18)
    w = int(max(ws) + pad[0] * 2); h = int(lh * len(lines) + pad[1] * 2 - (lh - size) * 0.6)
    sc = 0.85 + 0.15 * alpha
    layer = Image.new('RGBA', (w + 60, h + 60), (0, 0, 0, 0))
    sh = Image.new('RGBA', layer.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((30, 38, 30 + w, 38 + h), radius=radius, fill=(0, 0, 0, 70))
    sh = sh.filter(ImageFilter.GaussianBlur(12))
    layer.alpha_composite(sh)
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((30, 30, 30 + w, 30 + h), radius=radius, fill=bg + (245,))
    for i, l in enumerate(lines):
        d.text((30 + (w - ws[i]) / 2, 30 + pad[1] + i * lh - size * 0.12), l, font=f, fill=fg)
    if sc != 1:
        layer = layer.resize((max(1, int(layer.width * sc)), max(1, int(layer.height * sc))), Image.LANCZOS)
    a = layer.getchannel('A').point(lambda v: int(v * alpha)); layer.putalpha(a)
    img.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))

def steps_done(t):
    return max(0, min(NSTEP, int((t - F_BUILD - 4) / STEP_DT) + 1)) if t >= F_BUILD + 4 else 0

def overlay(img, t):
    # hook
    ha = 1.0 if t < 28 else (ease((34 - t) / 6) if t < 34 else 0.0)
    if t >= 468: ha = ease((t - 468) / 8)
    plate(img, W / 2, 270, ['Соберём', 'Змея Горыныча?'], 76, ha)
    # build
    a = pop(t, 34, 182)
    plate(img, W / 2, 230, ['37 шагов сборки'], 64, a)
    if a > 0:
        k = steps_done(t)
        plate(img, W / 2, 345, [f'шаг {max(k, 1)} из 37'], 46, a, bg=GREEN, fg=CREAM, weight=700, pad=(34, 18), radius=34)
    plate(img, W / 2, 250, ['Вперёд — 2 секунды'], 64, pop(t, F_GO, F_TURN + 2))
    a = pop(t, F_TURN + 2, F_BACK + 2)
    plate(img, W / 2, 230, ['Разворот — 1 секунда'], 64, a)
    plate(img, W / 2, 345, ['замедлено ×2'], 40, a, bg=GREEN, fg=CREAM, weight=700, pad=(30, 14), radius=30)
    plate(img, W / 2, 250, ['Обратно — 2 секунды'], 64, pop(t, F_BACK + 2, F_HOME + 4))
    plate(img, W / 2, 250, ['Вернулся домой!'], 68, pop(t, F_HOME + 4, F_CARD))
    card(img, pop(t, F_CARD, 468, 9))

def card(img, alpha):
    if alpha <= 0.01: return
    w, h = 900, 560
    layer = Image.new('RGBA', (w + 80, h + 80), (0, 0, 0, 0))
    sh = Image.new('RGBA', layer.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((40, 52, 40 + w, 52 + h), radius=48, fill=(0, 0, 0, 80))
    layer.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((40, 40, 40 + w, 40 + h), radius=48, fill=(255, 255, 255, 246))
    lg = LOGO.copy(); lg.thumbnail((130, 130)); layer.alpha_composite(lg, (40 + (w - lg.width) // 2, 80))
    def ctext(y, s, f, fill):
        tw = d.textlength(s, font=f); d.text((40 + (w - tw) / 2, y), s, font=f, fill=fill)
    ctext(240, 'Урок-сборка', font(800, 66), INK)
    ctext(320, '«Змей Горыныч»', font(800, 66), INK)
    ctext(410, 'LEGO SPIKE Essential · 7–9 лет', font(600, 36), (74, 88, 100))
    f = font(800, 44); tw = d.textlength('legobot.ru', font=f)
    x0 = 40 + (w - tw - 40) / 2
    d.rounded_rectangle((x0 - 30, 480, x0 + tw + 70, 560), radius=40, fill=GREEN)
    d.ellipse((x0, 510, x0 + 20, 530), fill=PINK)
    d.text((x0 + 38, 490), 'legobot.ru', font=f, fill=CREAM)
    sc = 0.9 + 0.1 * alpha
    layer = layer.resize((int(layer.width * sc), int(layer.height * sc)), Image.LANCZOS)
    layer.putalpha(layer.getchannel('A').point(lambda v: int(v * alpha)))
    img.alpha_composite(layer, (int(W / 2 - layer.width / 2), int(H * 0.40 - layer.height / 2)))

# ---------------- sound ----------------
SR = 44100
def synth():
    n = int(SR * N / FPS); out = np.zeros(n)
    tt = np.arange(n) / SR
    def note(t0, f, dur=0.5, amp=0.18, kind='marimba'):
        i0 = int(t0 * SR); m = min(n - i0, int(dur * SR))
        if m <= 0: return
        x = np.arange(m) / SR
        env = np.exp(-x * (7 if kind == 'marimba' else 3)) * np.minimum(1, x * 400)
        s = np.sin(2 * np.pi * f * x) + 0.35 * np.sin(2 * np.pi * f * 4 * x) * np.exp(-x * 25)
        out[i0:i0 + m] += amp * env * s
    # soft pentatonic loop, 100 bpm, 16 s -> loops cleanly
    scale = [261.6, 293.7, 329.6, 392.0, 440.0, 523.3, 587.3, 659.3]
    beat = 60 / 100 / 2
    pat = [0, 2, 4, 5, 4, 2, 3, 1, 0, 2, 4, 6, 5, 4, 2, 3]
    bass = [130.8, 130.8, 110.0, 98.0]
    k = 0; t = 0.0
    while t < N / FPS - 0.05:
        note(t, scale[pat[k % 16]], 0.45, 0.10)
        if k % 8 == 0: note(t, bass[(k // 8) % 4], 1.6, 0.12, 'pad')
        t += beat; k += 1
    # clicks: part lands
    for s in range(NSTEP):
        t0 = (F_BUILD + STEP_DT * s + 9) / FPS
        i0 = int(t0 * SR); m = int(0.04 * SR)
        x = np.arange(m) / SR
        out[i0:i0 + m] += 0.22 * np.exp(-x * 160) * (np.random.RandomState(s).randn(m) * 0.6 + np.sin(2 * np.pi * 1800 * x))
    # motor whirr while driving / turning
    for a0, a1 in ((F_GO, F_TURN), (F_TURN, F_BACK), (F_BACK, F_HOME)):
        i0, i1 = int(a0 / FPS * SR), int(a1 / FPS * SR); x = np.arange(i1 - i0) / SR
        L = len(x); env = np.minimum(1, np.minimum(x / 0.12, (L / SR - x) / 0.12))
        f0 = 140 if a0 != F_TURN else 95
        s = (np.sin(2 * np.pi * f0 * x) * 0.6 + np.sign(np.sin(2 * np.pi * f0 * 2 * x)) * 0.15) * (1 + 0.2 * np.sin(2 * np.pi * 11 * x))
        out[i0:i1] += 0.07 * env * s
    # whoosh when parts fly away + chime on card
    i0 = int(446 / FPS * SR); m = int(0.7 * SR); x = np.arange(m) / SR
    nz = np.random.RandomState(1).randn(m); nz = np.convolve(nz, np.ones(30) / 30, 'same')
    out[i0:i0 + m] += 0.5 * nz * np.sin(np.pi * x / 0.7) ** 2
    for j, f in enumerate((523.3, 659.3, 784.0)):
        note(F_CARD / FPS + j * 0.09, f, 1.2, 0.14)
    # fade tail so the loop joins softly
    out *= np.minimum(1, (n - np.arange(n)) / (0.25 * SR))
    out = out / max(1e-6, np.abs(out).max()) * 0.85
    pcm = (out * 32767).astype(np.int16)
    with wave.open(os.path.join(OUT, 'sound.wav'), 'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR); wf.writeframes(pcm.tobytes())

# ---------------- main ----------------
files = sorted(glob.glob(os.path.join(FR, 'f*.jpg')))
print('frames:', len(files))
comp = os.path.join(OUT, 'comp'); os.makedirs(comp, exist_ok=True)
done = []
for p in files:
    f = int(os.path.basename(p)[1:5])
    img = Image.open(p).convert('RGBA'); overlay(img, f)
    img.convert('RGB').save(os.path.join(comp, f'f{f:04d}.jpg'), quality=93); done.append(f)
    if TEST: img.convert('RGB').save(os.path.join(OUT, f'test_f{f:04d}.jpg'), quality=90)
# contact sheet
if done:
    th = [Image.open(os.path.join(comp, f'f{f:04d}.jpg')).resize((270, 480)) for f in done[:: max(1, len(done) // 12)][:12]]
    sheet = Image.new('RGB', (270 * min(6, len(th)), 480 * ((len(th) + 5) // 6)), 'white')
    for i, im in enumerate(th): sheet.paste(im, ((i % 6) * 270, (i // 6) * 480))
    sheet.save(os.path.join(OUT, 'sheet.jpg'), quality=88)
# post stills with caption
for name in ('post',):
    p = os.path.join(FR, name + '.jpg')
    if not os.path.exists(p): continue
    im = Image.open(p).convert('RGBA'); Wd, Hd = im.size
    im.convert('RGB').save(os.path.join(OUT, name + '_clean.jpg'), quality=95)
    s1, s2 = int(Wd * 0.048), int(Wd * 0.022)
    f1, f2 = font(800, s1), font(600, s2)
    lay = Image.new('RGBA', im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    lines = [('Змей Горыныч', f1, INK, s1), ('урок-сборка · LEGO SPIKE Essential', f2, (74, 88, 100), s2), ('legobot.ru', font(800, s2), GREEN, s2)]
    pad = int(Wd * 0.03); bw = max(d.textlength(t, font=f) for t, f, _, _ in lines) + 2 * pad
    bh = s1 * 1.25 + s2 * 1.45 * 2 + 2 * pad
    x0, y0 = Wd * 0.045, Hd - bh - Hd * 0.06
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=int(Wd * 0.025), fill=(255, 255, 255, 242))
    yy = y0 + pad - s1 * 0.12
    for t, f, col, sz in lines:
        d.text((x0 + pad, yy), t, font=f, fill=col); yy += sz * (1.25 if sz == s1 else 1.45)
    im.alpha_composite(lay); im = im.convert('RGB')
    im.save(os.path.join(OUT, name + '.jpg'), quality=95)
    im.resize((1280, 960), Image.LANCZOS).save(os.path.join(OUT, 'post_tg_1280.jpg'), quality=95)
if not TEST and len(done) == N:
    synth()
    # reel cover
    cv = Image.open(os.path.join(FR, f'f{F_GO - 6:04d}.jpg')).convert('RGBA')
    plate(cv, W / 2, 360, ['Змей Горыныч', 'из LEGO SPIKE'], 84, 1.0)
    plate(cv, W / 2, 545, ['урок-сборка · 37 шагов'], 46, 1.0, bg=GREEN, fg=CREAM, weight=700, pad=(34, 18), radius=34)
    cv.convert('RGB').save(os.path.join(OUT, 'cover.jpg'), quality=94)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', os.path.join(comp, 'f%04d.jpg'),
                    '-i', os.path.join(OUT, 'sound.wav'), '-c:v', 'libx264', '-preset', 'slow', '-crf', '17',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart',
                    os.path.join(OUT, 'gorynych_reel.mp4')], check=True)
    print('video ok')

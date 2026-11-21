#!/usr/bin/env python3
"""Builds the profile README and its SVG cards from profile.json.

    python build/build.py         everything
    python build/build.py --city  only the commit city (what the daily workflow runs)

GitHub strips CSS, scripts and web fonts from READMEs, but it shows SVG images, and an SVG
can carry its own fonts, styles and animations. So every block here is an SVG with
Source Serif 4 and JetBrains Mono embedded (subset), animated with CSS and SMIL.
"""
import base64, datetime, io, json, os, re, sys, urllib.request
from xml.sax.saxutils import escape
from fontTools.ttLib import TTFont
from fontTools import subset
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")

C = {
    # neutral near-black, clean greys, and a true red accent (hue 356, no orange in it)
    "panel": "#0b0b0c", "card": "#121214", "edge": "#26262b",
    "ink": "#f5f5f7", "ink2": "#bcbcc4", "muted": "#85858f", "faint": "#4c4c55",
    "accent": "#ff1f2d", "accent2": "#ff5c66", "grid": "rgba(255,31,45,0.045)",
    # tag colours: reds and neutrals only
    "red": "#ff1f2d", "crimson": "#e0101e", "rose": "#ff5c66", "white": "#e9e9ee", "steel": "#9a9aa6",
}

FONT_FILES = {
    ("serif", 400, "normal"): "SourceSerif4-Regular.ttf",
    ("serif", 500, "normal"): "SourceSerif4-Medium.ttf",
    ("serif", 400, "italic"): "SourceSerif4-Italic.ttf",
    ("serif", 500, "italic"): "SourceSerif4-MediumItalic.ttf",
    ("mono", 400, "normal"): "JetBrainsMono-Regular.ttf",
    ("mono", 500, "normal"): "JetBrainsMono-Medium.ttf",
}
FAMILY = {
    "serif": "FSerif, 'Source Serif 4', Georgia, serif",
    "mono": "FMono, 'JetBrains Mono', Consolas, monospace",
}
CHARSET = "".join(chr(c) for c in range(0x20, 0x7F)) + "·→←—–’‘“”…•°×é"


# ---------------------------------------------------------------- fonts

class Font:
    def __init__(self, key):
        self.path = os.path.join(HERE, "fonts", FONT_FILES[key])
        tt = TTFont(self.path)
        self.upm = tt["head"].unitsPerEm
        self.cmap = tt.getBestCmap()
        self.hmtx = tt["hmtx"].metrics
        self._b64 = None

    def width(self, text, size, ls=0.0):
        units = sum(self.hmtx[self.cmap.get(ord(ch)) or self.cmap[ord("?")]][0] for ch in text)
        return units * size / self.upm + ls * len(text)

    def b64(self):
        if self._b64 is None:
            opts = subset.Options()
            opts.flavor = "woff"
            opts.layout_features = ["kern", "liga"]
            tt = TTFont(self.path)
            sub = subset.Subsetter(opts)
            sub.populate(text=CHARSET)
            sub.subset(tt)
            buf = io.BytesIO()
            tt.flavor = "woff"
            tt.save(buf)
            self._b64 = base64.b64encode(buf.getvalue()).decode()
        return self._b64


FONTS = {k: Font(k) for k in FONT_FILES}


def fnt(fam, weight=400, style="normal"):
    return FONTS[(fam, weight, style)]


def wrap(text, fam, size, maxw, weight=400, ls=0.0):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if fnt(fam, weight).width(trial, size, ls) <= maxw or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


def fit(text, fam, size, maxw, weight=400, ls=0.0):
    if fnt(fam, weight).width(text, size, ls) <= maxw:
        return text
    while text and fnt(fam, weight).width(text + "…", size, ls) > maxw:
        text = text[:-1]
    return text.rstrip(" ,.") + "…"


def segments(text):
    return [(part, i % 2 == 1) for i, part in enumerate(text.split("*")) if part]


def image_uri(name, max_w=900, quality=88):
    im = Image.open(os.path.join(HERE, "images", name)).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(), im.width / im.height


# ---------------------------------------------------------------- svg writer

class Svg:
    def __init__(self, w, h, label):
        self.w, self.h, self.label = w, h, label
        self.parts, self.defs, self.css, self.used = [], [], set(), set()

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, fam="serif", size=16, weight=400, style="normal", fill=C["ink"],
             anchor="start", ls=0.0, upper=False, cls=""):
        self.used.add((fam, weight, style))
        s = s.upper() if upper else s
        a = f'x="{x:.1f}" y="{y:.1f}" class="{fam[0]} {cls}" font-size="{size}" fill="{fill}"'
        a += f' font-weight="{weight}"' if weight != 400 else ""
        a += f' font-style="{style}"' if style != "normal" else ""
        a += f' text-anchor="{anchor}"' if anchor != "start" else ""
        a += f' letter-spacing="{ls}"' if ls else ""
        self.add(f"<text {a}>{escape(s)}</text>")

    def rich(self, x, y, s, size, weight=500, fill=C["ink"], accent=C["accent"]):
        spans = []
        for part, it in segments(s):
            self.used.add(("serif", weight, "italic" if it else "normal"))
            spans.append(f'<tspan font-style="italic" fill="{accent}">{escape(part)}</tspan>' if it else escape(part))
        self.add(f'<text x="{x}" y="{y}" class="s" font-size="{size}" font-weight="{weight}" '
                 f'fill="{fill}" letter-spacing="-0.01em">{"".join(spans)}</text>')

    def panel(self, grid=True, r=12):
        self.add(f'<rect x="0.5" y="0.5" width="{self.w-1}" height="{self.h-1}" rx="{r}" fill="{C["panel"]}" stroke="{C["edge"]}"/>')
        if grid:
            self.defs.append(f'<pattern id="grid" width="16" height="16" patternUnits="userSpaceOnUse">'
                             f'<path d="M16 0H0V16" fill="none" stroke="{C["grid"]}" stroke-width="1"/></pattern>')
            self.add(f'<rect x="1" y="1" width="{self.w-2}" height="{self.h-2}" rx="{r}" fill="url(#grid)"/>')

    def render(self):
        faces = []
        for fam, weight, style in sorted(self.used):
            faces.append(f"@font-face{{font-family:{'FSerif' if fam == 'serif' else 'FMono'};font-weight:{weight};"
                         f"font-style:{style};src:url(data:font/woff;base64,{fnt(fam, weight, style).b64()}) format('woff')}}")
        css = "".join(faces) + (
            f".s{{font-family:{FAMILY['serif']};font-optical-sizing:auto;text-rendering:optimizeLegibility}}"
            f".m{{font-family:{FAMILY['mono']};font-variant-ligatures:none;font-feature-settings:'liga' 0,'calt' 0}}"
            "*{transform-box:view-box}"
        ) + "".join(sorted(self.css)) + "@media (prefers-reduced-motion:reduce){.a{animation:none!important}}"
        return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" role="img" '
                f'aria-label="{escape(self.label)}"><title>{escape(self.label)}</title><style>{css}</style>'
                f"<defs>{''.join(self.defs)}</defs>{''.join(self.parts)}</svg>")

    def save(self, name):
        os.makedirs(ASSETS, exist_ok=True)
        path = os.path.join(ASSETS, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.render())
        print(f"  assets/{name:<24} {os.path.getsize(path) // 1024:>4} KB")


def typer(s, x, y, prompt, phrases):
    """'$ now building ' then each phrase types itself out, holds, and gives way to the next."""
    size, slot, typing = 14, 3.6, 1.4
    T = slot * len(phrases)
    s.text(x, y, prompt, "mono", size, fill=C["muted"])
    px = x + fnt("mono").width(prompt, size)
    cw = fnt("mono").width("M", size)
    for k, p in enumerate(phrases):
        a, b, t = 100 * k * slot / T, 100 * (k + 1) * slot / T, 100 * (k * slot + typing) / T
        tw = cw * len(p)
        s.css.add(f"@keyframes v{k}{{0%{{opacity:0}}{a:.2f}%{{opacity:1}}{b:.2f}%{{opacity:0}}100%{{opacity:0}}}}"
                  f".v{k}{{opacity:0;animation:v{k} {T}s steps(1,end) infinite}}"
                  f"@keyframes t{k}{{0%{{transform:translateX(0);animation-timing-function:steps(1,end)}}"
                  f"{a:.2f}%{{transform:translateX(0);animation-timing-function:steps({len(p)},end)}}"
                  f"{t:.2f}%{{transform:translateX({tw:.1f}px);animation-timing-function:steps(1,end)}}"
                  f"100%{{transform:translateX({tw:.1f}px)}}}}"
                  f".t{k}{{animation:t{k} {T}s infinite}}")
        s.used.add(("mono", 400, "normal"))
        s.add(f'<g class="a v{k}"><text x="{px:.1f}" y="{y}" class="m" font-size="{size}" fill="{C["accent"]}">{escape(p)}</text>'
              f'<g class="a t{k}"><rect x="{px:.1f}" y="{y-size}" width="{tw+cw*2:.1f}" height="{size+6}" fill="{C["panel"]}"/>'
              f'<rect class="a caret" x="{px+1:.1f}" y="{y-size+2}" width="{cw*0.6:.1f}" height="{size+1}" fill="{C["accent"]}"/></g></g>')
    s.css.add("@keyframes blink{50%{opacity:0}}.caret{animation:blink 1s steps(1) infinite}")
    # reduced motion: show the first phrase, fully typed
    s.css.add(f"@media (prefers-reduced-motion:reduce){{.v0{{opacity:1}}.t0{{transform:translateX({cw*len(phrases[0]):.1f}px)}}}}")


def divider(num, title):
    W, H = 1000, 44
    label = f"{num}  ·  {title.upper()}"
    lw = fnt("mono", 500).width(label, 12, 1.4)
    s = Svg(W, H, f"{num} · {title}")
    left_end, right_start = W / 2 - lw / 2 - 20, W / 2 + lw / 2 + 20
    x = 2.0
    while x + 4 <= left_end:
        s.add(f'<rect x="{x:.1f}" y="20" width="4" height="4" fill="#2a2a30"/>')
        x += 9
    x = W - 6
    while x >= right_start:
        s.add(f'<rect x="{x:.1f}" y="20" width="4" height="4" fill="#2a2a30"/>')
        x -= 9
    s.used.add(("mono", 500, "normal"))
    s.add(f'<text x="500" y="26.5" class="m" font-size="12" font-weight="500" letter-spacing="1.4" '
          f'text-anchor="middle" fill="{C["muted"]}"><tspan fill="{C["accent"]}">{num}</tspan>'
          f'  ·  {escape(title.upper())}</text>')
    s.save(f"divider-{num}.svg")


def stack(cfg):
    """A small, quiet panel: what I use, without making a show of it."""
    W, H = 1000, 112
    groups = cfg["stack"]
    s = Svg(W, H, "Toolbox. " + ". ".join(f'{g["label"]}: {", ".join(g["items"])}' for g in groups))
    s.add(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="10" fill="{C["panel"]}" stroke="{C["edge"]}"/>')
    s.text(28, 32, "Toolbox", "mono", 10, 500, fill=C["faint"], ls=1.6, upper=True)
    for i, g in enumerate(groups):
        x, y = 28 + (i % 2) * 486, 62 + (i // 2) * 28
        s.add(f'<rect x="{x}" y="{y-7}" width="4" height="4" fill="{C["accent"]}" opacity="0.7"/>')
        s.text(x + 14, y, g["label"], "mono", 10, 500, fill=C["muted"], ls=1.3, upper=True)
        s.text(x + 120, y, "  ·  ".join(g["items"]), "mono", 12, fill=C["ink2"])
    s.save("stack.svg")


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def link_button(l):
    tw = fnt("mono", 500).width(l["label"].upper(), 12, 1.4)
    W, H = int(tw + 64), 44
    s = Svg(W, H, l["label"])
    s.add(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="8" fill="{C["panel"]}" stroke="{C["edge"]}"/>')
    s.add(f'<rect x="20" y="18" width="8" height="8" fill="{C[l["color"]]}"/>')
    s.text(38, 26.5, l["label"], "mono", 12, 500, fill=C["ink"], ls=1.4, upper=True)
    s.save(f"link-{slug(l['label'])}.svg")



# ---------------------------------------------------------------- pixel scenes
# Every scene is pixel art drawn here in code, about things I build: a TVC rocket launch,
# a LiDAR scan, a night skyline, and the Batcave. Pixels are SVG rects (runs merged per row,
# crispEdges), so they stay sharp at any size. Moving parts are separate sprites animated with
# CSS steps(), so they move one pixel at a time like real pixel art.

import numpy as np

BAYER = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) + 0.5) / 16

PX = {   # the scene palette: neutral blacks and greys, true reds, a little white
    "void": "#0b0b0c", "night1": "#0f0b0c", "night2": "#170a0c", "night3": "#22090d", "night4": "#33090f",
    "glow": "#4d0a12", "hill1": "#1a0d0f", "hill2": "#111012", "ground": "#0d0d0f", "rim": "#6e0b15",
    "red": "#ff1f2d", "red2": "#e0101e", "red3": "#a50d18", "red4": "#6a0a12",
    "pink": "#ff8a94", "white": "#f5f5f7", "grey": "#9a9aa3", "grey2": "#55555d", "grey3": "#2c2c32",
    "steel": "#3a3a42", "black": "#050506",
}


def mix(a, b, t):
    ca = np.array([int(a[i:i + 2], 16) for i in (1, 3, 5)])
    cb = np.array([int(b[i:i + 2], 16) for i in (1, 3, 5)])
    c = ca * (1 - t) + cb * t
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in c)


class Pix:
    """A grid of colours (or None). Rendered as merged rects at pixel size P."""

    def __init__(self, gw, gh):
        self.gw, self.gh = gw, gh
        self.g = [[None] * gw for _ in range(gh)]

    def set(self, x, y, c):
        x, y = int(x), int(y)
        if 0 <= x < self.gw and 0 <= y < self.gh:
            self.g[y][x] = c

    def get(self, x, y):
        return self.g[y][x] if 0 <= x < self.gw and 0 <= y < self.gh else None

    def rect(self, x, y, w, h, c):
        for yy in range(int(y), int(y + h)):
            for xx in range(int(x), int(x + w)):
                self.set(xx, yy, c)

    def sprite(self, x, y, art, cmap):
        for j, row in enumerate(art):
            for i, ch in enumerate(row):
                if ch in cmap:
                    self.set(x + i, y + j, PX.get(cmap[ch], cmap[ch]))

    def sky(self, stops, y0=0, y1=None):
        """Vertical gradient between palette stops, dithered like old games."""
        y1 = self.gh if y1 is None else y1
        n = len(stops) - 1
        for y in range(y0, y1):
            t = (y - y0) / max(1, y1 - y0 - 1) * n
            for x in range(self.gw):
                i = min(n, int(t + BAYER[y % 4, x % 4] - 0.5 + 0.5))
                self.set(x, y, PX.get(stops[i], stops[i]))

    def fade(self, l=0.0, r=0.0, t=0.0, b=0.0, seed=1):
        """Dissolve edges into the page: pixels thin out and darken towards the edge."""
        rnd = np.random.default_rng(seed).random((self.gh, self.gw))
        for y in range(self.gh):
            for x in range(self.gw):
                k = 1.0
                if l: k = min(k, (x + 0.5) / (l * self.gw))
                if r: k = min(k, (self.gw - x - 0.5) / (r * self.gw))
                if t: k = min(k, (y + 0.5) / (t * self.gh))
                if b: k = min(k, (self.gh - y - 0.5) / (b * self.gh))
                if k >= 1 or self.g[y][x] is None:
                    continue
                k = max(0.0, k)
                if k < 0.45 * BAYER[y % 4, x % 4] + 0.55 * rnd[y, x]:
                    self.g[y][x] = None
                else:
                    self.g[y][x] = mix(self.g[y][x], C["panel"], (1 - k) * 0.7)

    def svg(self, P, x0=0, y0=0):
        out = []
        for y in range(self.gh):
            x = 0
            row = self.g[y]
            while x < self.gw:
                c = row[x]
                if c is None:
                    x += 1
                    continue
                x1 = x
                while x1 < self.gw and row[x1] == c:
                    x1 += 1
                out.append(f'<rect x="{x0 + x*P:g}" y="{y0 + y*P:g}" width="{(x1-x)*P:g}" height="{P:g}" fill="{c}"/>')
                x = x1
        return "".join(out)


def sprite_svg(art, cmap, P, x0, y0):
    p = Pix(max(len(r) for r in art), len(art))
    p.sprite(0, 0, art, cmap)
    return p.svg(P, x0, y0)


def disc(p, cx, cy, r, colour_at):
    for y in range(int(cy - r - 1), int(cy + r + 2)):
        for x in range(int(cx - r - 1), int(cx + r + 2)):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                c = colour_at(x, y)
                if c:
                    p.set(x, y, c)


def hills(p, base, amp, freq, phase, colour, rim=None):
    for x in range(p.gw):
        top = int(round(base - amp * (0.6 * np.sin(x * freq + phase) + 0.4 * np.sin(x * freq * 2.3 + phase * 1.7))))
        for y in range(max(0, top), p.gh):
            p.set(x, y, colour)
        if rim:
            p.set(x, top, rim)


def stars(s, p, P, x0, y0, n, ymax, seed, twinkle=0.4):
    rnd = np.random.default_rng(seed)
    s.css.add("@keyframes tw{0%,100%{opacity:.15}50%{opacity:1}}.tw{animation:tw 3s steps(4) infinite}")
    out = []
    for _ in range(n):
        x, y = rnd.integers(0, p.gw), rnd.integers(0, ymax)
        col = PX["white"] if rnd.random() < 0.7 else PX["pink"]
        if rnd.random() < twinkle:
            out.append(f'<rect class="a tw" style="animation-delay:-{rnd.random()*3:.1f}s;animation-duration:{2+rnd.random()*3:.1f}s" '
                       f'x="{x0+x*P}" y="{y0+y*P}" width="{P}" height="{P}" fill="{col}"/>')
        else:
            p.set(x, y, mix(col, PX["void"], 0.45))
    return "".join(out)


# --- sprites ---------------------------------------------------------------

ROCKET = [
    "...w...",
    "..www..",
    "..www..",
    ".wwwww.",
    ".wwRww.",
    ".wwwww.",
    ".wgwww.",
    ".wwwww.",
    ".wwwww.",
    "RwwwwwR",
    "RRwwwRR",
    "R.sss.R",
]
FLAME = [
    [".rppr.", "..rhr..", "..rpr..", "...r...", "...d..."],
    [".rpppr.", ".rphpr.", "..rpr..", "..rd...", "..d...."],
    [".rpppr.", ".rphpr.", "..rpr..", "...dr..", "....d.."],
]
FLAME_MAP = {"h": "white", "p": "pink", "r": "red", "d": "red3"}
ROCKET_MAP = {"w": "white", "R": "red", "g": "grey", "s": "grey2"}

BAT = [
    ["b.......b", "bb.....bb", ".bbb.bbb.", "..bbbbb..", "....b...."],
    ["....b....", "..bbbbb..", ".bbbbbbb.", "bb..b..bb", "b.......b"],
]
DRONE = [
    ["ww.....ww", ".g.....g.", ".ggggggg.", "...ggg...", "........."],
    ["-w.....w-", ".g.....g.", ".ggggggg.", "...ggg...", "........."],
]
ROVER = [
    "....RR....",
    ".....g....",
    ".gggggggg.",
    "gggggggggg",
    ".o..o..o..",
]


def launch_scene(s, x0, y0, W, H, P=5):
    gw, gh = W // P, H // P
    p = Pix(gw, gh)
    ground = gh - 10
    p.sky(["void", "night1", "night2", "night3", "night4", "glow"], 0, ground)
    # striped synthwave sun, sinking behind the hills
    cx, cy, r = int(gw * 0.74), ground - 13, 14

    def sun(x, y):
        if y > cy - 2 and (y - cy + 2) % 3 == 0:   # the stripes get closer near the horizon
            return None
        t = (y - (cy - r)) / (2 * r)
        return mix(PX["red"], PX["red4"], max(0, min(1, t)) ** 1.2)
    disc(p, cx, cy, r, sun)
    hills(p, ground - 4, 4, 0.045, 1.2, PX["hill1"], PX["rim"])
    hills(p, ground + 1, 3, 0.08, 4.0, PX["hill2"], PX["red4"])
    p.rect(0, ground + 2, gw, gh - ground - 2, PX["ground"])
    for y in range(ground + 2, gh):   # ground darkens into the page
        for x in range(gw):
            if (y - ground) / (gh - ground) > BAYER[y % 4, x % 4] + 0.25:
                p.set(x, y, C["panel"])
    # launch tower: a lattice with a warning light
    tx, pad = int(gw * 0.13), ground + 1
    for y in range(pad - 22, pad):
        p.set(tx, y, PX["steel"]); p.set(tx + 3, y, PX["steel"])
        if y % 3 == 0:
            p.rect(tx, y, 4, 1, PX["steel"])
        elif y % 3 == 1:
            p.set(tx + 1, y, PX["grey3"]); p.set(tx + 2, y, PX["grey3"])
    for i in range(3):
        p.set(tx + 4 + i, pad - 18 + i * 6, PX["grey3"])
    p.rect(tx - 2, pad, 14, 1, PX["steel"])
    star_svg = stars(s, p, P, x0, y0, 42, ground - 14, seed=4)
    p.fade(l=0.04, r=0.04)
    s.add(f'<g shape-rendering="crispEdges">{p.svg(P, x0, y0)}{star_svg}')
    # tower light
    s.css.add("@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:.1}}.blink{animation:blink 1.2s steps(1) infinite}")
    s.add(f'<rect class="a blink" x="{x0+(tx+1)*P}" y="{y0+(pad-23)*P}" width="{2*P}" height="{P}" fill="{PX["red"]}"/>')
    # shooting star now and then
    s.css.add("@keyframes shoot{0%{transform:translate(0,0);opacity:0}2%{opacity:1}10%{transform:translate(-240px,120px);opacity:0}100%{opacity:0}}"
              ".shoot{opacity:0;animation:shoot 11s steps(24) infinite 3s}")
    sx, sy = x0 + int(gw * 0.55) * P, y0 + 3 * P
    s.add(f'<g class="a shoot">' + "".join(
        f'<rect x="{sx+i*P}" y="{sy-i*P//2}" width="{P}" height="{P}" fill="{mix(PX["white"], PX["void"], i/5)}"/>' for i in range(5)) + "</g>")
    # the rocket: ignites, its flame swings like a gimballed motor, climbs, gone, again
    rx = x0 + (tx + 5) * P
    ry = y0 + (pad - len(ROCKET)) * P
    T = 9
    s.css.add(
        f"@keyframes lift{{0%,22%{{transform:translateY(0);opacity:1}}"
        f"45%{{transform:translateY(-40px)}}62%{{transform:translateY(-130px)}}"
        f"80%{{transform:translateY(-{H+20}px);opacity:1}}80.5%,100%{{transform:translateY(-{H+20}px);opacity:0}}}}"
        f".lift{{animation:lift {T}s steps(90) infinite}}"
        f"@keyframes ign{{0%,9%{{opacity:0}}10%,80%{{opacity:1}}81%,100%{{opacity:0}}}}.ign{{animation:ign {T}s steps(1) infinite}}"
        "@keyframes fA{0%,32%{opacity:1}33%,100%{opacity:0}}@keyframes fB{0%,32%{opacity:0}33%,65%{opacity:1}66%,100%{opacity:0}}"
        "@keyframes fC{0%,65%{opacity:0}66%,100%{opacity:1}}"
        ".fA{animation:fA .36s steps(1) infinite}.fB{animation:fB .36s steps(1) infinite}.fC{animation:fC .36s steps(1) infinite}"
        f"@keyframes puff{{0%,10%{{opacity:0}}12%,30%{{opacity:1}}40%,100%{{opacity:0}}}}.puff{{animation:puff {T}s steps(1) infinite}}"
        f"@keyframes trail{{0%,24%{{opacity:0}}28%,80%{{opacity:1}}81%,100%{{opacity:0}}}}.trail{{animation:trail {T}s steps(1) infinite}}")
    flames = "".join(f'<g class="a f{k}">{sprite_svg(FLAME[i], FLAME_MAP, P, rx, ry + len(ROCKET)*P)}</g>' for i, k in enumerate("ABC"))
    trail = "".join(f'<rect x="{rx+3*P}" y="{ry+(len(ROCKET)+5+i)*P}" width="{P}" height="{P}" '
                    f'fill="{mix(PX["grey2"], PX["void"], i/14)}"/>' for i in range(0, 14, 1 if True else 2))
    s.add(f'<g class="a lift">{sprite_svg(ROCKET, ROCKET_MAP, P, rx, ry)}'
          f'<g class="a ign">{flames}</g><g class="a trail">{trail}</g></g>')
    puff = Pix(17, 3)
    for i, c in enumerate([".gg..ggg...gg..g.", "ggggggggggggggggg", ".g.ggg...ggg.g..."]):
        for j, ch in enumerate(c):
            if ch == "g":
                puff.set(j, i, PX["grey3"] if i else PX["steel"])
    s.add(f'<g class="a puff">{puff.svg(P, rx - 5*P, y0 + (pad-2)*P)}</g>')
    s.add("</g>")


def lidar_scene(s, x0, y0, W, H, P=5):
    gw, gh = W // P, H // P
    p = Pix(gw, gh)
    p.sky(["void", "void", "night1", "night2", "night3"], 0, gh)
    surface = []
    tops = [int(round(gh - 7 - 1.6 * np.sin(x / 9) - np.sin(x / 4.3 + 1))) for x in range(gw)]
    rnd = np.random.default_rng(9)
    for x in range(gw):
        for y in range(tops[x], gh):
            p.set(x, y, PX["ground"])
        surface.append((x, tops[x]))
    for _ in range(9):   # rocks
        rx_, w = rnd.integers(50, gw - 6), rnd.integers(2, 4)
        hgt = rnd.integers(1, 3)
        for i in range(w):
            for j in range(hgt):
                p.set(rx_ + i, tops[rx_ + i] - 1 - j, PX["ground"])
            surface.append((rx_ + i, tops[rx_ + i] - hgt))
    star_svg = stars(s, p, P, x0, y0, 22, gh - 9, seed=12, twinkle=0.3)
    p.fade(l=0.22, r=0.12, t=0.15, b=0.1, seed=3)
    s.add(f'<g shape-rendering="crispEdges">{p.svg(P, x0, y0)}{star_svg}')
    T = 4.0
    s.css.add(f"@keyframes ping{{0%{{opacity:1}}25%{{opacity:.25}}100%{{opacity:.25}}}}.ping{{animation:ping {T}s linear infinite}}"
              f"@keyframes sweep{{from{{transform:translateX(0)}}to{{transform:translateX({W}px)}}}}"
              f".sweep{{animation:sweep {T}s steps({gw}) infinite}}")
    # point cloud: every surface pixel lights up as the scan line passes it
    for (x, y) in surface:
        if x < 34:
            continue
        col = PX["red"] if (x + y) % 3 else PX["pink"]
        s.add(f'<rect class="a ping" style="animation-delay:{x/gw*T - T:.2f}s" x="{x0+x*P}" y="{y0+(y-1)*P}" '
              f'width="{P}" height="{P}" fill="{col}" opacity=".25"/>')
    beam = "".join(f'<rect x="{x0}" y="{y0+j*P}" width="{P}" height="{P}" fill="{PX["red"]}" opacity="{0.15+0.6*j/gh:.2f}"/>' for j in range(gh - 4))
    s.add(f'<g class="a sweep">{beam}</g>')
    rx = 40
    s.add(sprite_svg(ROVER, {"R": "red", "g": "grey", "o": "grey2"}, P, x0 + rx * P, y0 + (tops[rx + 4] - len(ROVER)) * P))
    s.add(f'<rect class="a blink" x="{x0+(rx+4)*P}" y="{y0+(tops[rx+4]-len(ROVER))*P}" width="{2*P}" height="{P}" fill="{PX["white"]}"/>')
    s.css.add("@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:.1}}.blink{animation:blink 1.2s steps(1) infinite}")
    s.add("</g>")


def skyline_scene(s, x0, y0, W, H, P=5):
    gw, gh = W // P, H // P
    p = Pix(gw, gh)
    p.sky(["void", "void", "night1", "night2", "night3", "night4"], 0, gh)
    rnd = np.random.default_rng(21)
    lights, x = [], 0
    while x < gw:
        bw, bh = int(rnd.integers(4, 10)), int(rnd.integers(5, gh - 3))
        col = PX["hill2"] if rnd.random() < 0.5 else "#151518"
        p.rect(x, gh - bh, bw, bh, col)
        for wy in range(gh - bh + 2, gh - 1, 2):
            for wx in range(x + 1, x + bw - 1, 2):
                r = rnd.random()
                if r < 0.30:
                    c = PX["red3"] if r < 0.22 else (PX["white"] if r < 0.25 else PX["pink"])
                    if rnd.random() < 0.18:
                        lights.append((wx, wy, c))
                    else:
                        p.set(wx, wy, mix(c, col, 0.25))
        if bh > gh - 8 and bw >= 5:
            p.rect(x + bw // 2, gh - bh - 3, 1, 3, PX["steel"])
            lights.append((x + bw // 2, gh - bh - 4, "antenna"))
        x += bw + int(rnd.integers(0, 2))
    star_svg = stars(s, p, P, x0, y0, 18, 6, seed=31, twinkle=0.5)
    p.fade(l=0.25, r=0.1, t=0.2, seed=5)
    s.add(f'<g shape-rendering="crispEdges">{p.svg(P, x0, y0)}{star_svg}')
    s.css.add("@keyframes win{0%,100%{opacity:.2}50%{opacity:1}}.win{animation:win 3.4s steps(3) infinite}"
              "@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:.1}}.blink{animation:blink 1.2s steps(1) infinite}")
    for (lx, ly, c) in lights:
        if lx < gw * 0.18:
            continue
        if c == "antenna":
            s.add(f'<rect class="a blink" style="animation-delay:-{rnd.random():.2f}s" x="{x0+lx*P}" y="{y0+ly*P}" width="{P}" height="{P}" fill="{PX["red"]}"/>')
        else:
            s.add(f'<rect class="a win" style="animation-delay:-{rnd.random()*3:.1f}s" x="{x0+lx*P}" y="{y0+ly*P}" width="{P}" height="{P}" fill="{c}"/>')
    # a drone crosses the skyline, rotors flickering, red light blinking
    s.css.add(f"@keyframes fly{{from{{transform:translateX(0)}}to{{transform:translateX({W+60}px)}}}}"
              f".fly{{animation:fly 16s steps({(W+60)//P}) infinite}}"
              "@keyframes bob{0%,49%{transform:translateY(0)}50%,100%{transform:translateY(-5px)}}.bob{animation:bob 1.6s steps(1) infinite}"
              "@keyframes rA{0%,49%{opacity:1}50%,100%{opacity:0}}@keyframes rB{0%,49%{opacity:0}50%,100%{opacity:1}}"
              ".rA{animation:rA .2s steps(1) infinite}.rB{animation:rB .2s steps(1) infinite}")
    dx, dy = x0 - 60, y0 + 3 * P
    dmap = {"w": "grey", "-": "grey2", "g": "steel"}
    s.add(f'<g class="a fly"><g class="a bob"><g class="a rA">{sprite_svg(DRONE[0], dmap, P, dx, dy)}</g>'
          f'<g class="a rB">{sprite_svg(DRONE[1], dmap, P, dx, dy)}</g>'
          f'<rect class="a blink" x="{dx+4*P}" y="{dy+4*P}" width="{P}" height="{P}" fill="{PX["red"]}"/></g></g>')
    s.add("</g>")


def batcave_scene(s, x0, y0, W, H, P=5):
    gw, gh = W // P, H // P
    p = Pix(gw, gh)
    p.sky(["void", "night1", "night2", "night3", "night4"], 0, gh)
    mx, my, mr = int(gw * 0.42), 15, 11

    def moon(x, y):
        t = ((x - mx) + (y - my)) / (2 * mr) + 0.5
        c = mix(PX["red"], PX["red3"], max(0, min(1, t)))
        if (x, y) in {(mx - 4, my - 2), (mx - 3, my - 2), (mx + 3, my + 4), (mx + 2, my + 5), (mx + 5, my - 4)}:
            c = PX["red4"]
        return c
    disc(p, mx, my, mr, moon)
    # cliff with a cave mouth on the right
    rnd0 = np.random.default_rng(5)
    for x in range(gw):
        t = (x - gw * 0.58) / (gw * 0.42)
        top = int(gh - 5 - max(0, t) ** 0.55 * (gh - 9) + (rnd0.integers(-1, 2) if t > 0.05 else 0)) if t > 0 else gh - 4
        for y in range(top, gh):
            p.set(x, y, "#18181c" if (x * 7 + y * 3) % 11 else "#1f1f24")
        if t > 0:
            p.set(x, top, PX["red3"])
            p.set(x, top + 1, PX["red4"])
    cx, cy = int(gw * 0.82), gh - 10
    for y in range(cy - 7, gh - 3):
        for x in range(cx - 9, cx + 10):
            if ((x - cx) / 9.5) ** 2 + ((y - cy) / 7.5) ** 2 <= 1:
                p.set(x, y, PX["black"])
    for rx_ in (cx - 5, cx + 1):           # two server racks inside the cave
        p.rect(rx_, cy - 4, 4, 10, PX["steel"])
        p.rect(rx_ + 1, cy - 3, 2, 8, PX["grey3"])
    p.rect(0, gh - 3, gw, 3, PX["ground"])
    star_svg = stars(s, p, P, x0, y0, 40, gh - 12, seed=8)
    p.fade(l=0.12, r=0.03, t=0.08, b=0.08, seed=9)
    s.add(f'<g shape-rendering="crispEdges">{p.svg(P, x0, y0)}{star_svg}')
    rnd = np.random.default_rng(2)
    s.css.add("@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:.1}}.blink{animation:blink 1.2s steps(1) infinite}")
    for k, rx_ in enumerate((cx - 5, cx + 1)):   # rack LEDs, one column per rack
        for j in range(4):
            col = PX["red"] if (j + k) % 3 else PX["white"]
            s.add(f'<rect class="a blink" style="animation-duration:{0.5+rnd.random()*1.5:.1f}s;animation-delay:-{rnd.random():.1f}s" '
                  f'x="{x0+(rx_+1)*P}" y="{y0+(cy-3+j*2)*P}" width="{P}" height="{P}" fill="{col}"/>')
    # bats leave the cave and cross the moon
    s.css.add("@keyframes wA{0%,49%{opacity:1}50%,100%{opacity:0}}@keyframes wB{0%,49%{opacity:0}50%,100%{opacity:1}}"
              ".wA{animation:wA .3s steps(1) infinite}.wB{animation:wB .3s steps(1) infinite}")
    for i in range(4):
        dur = 7 + i * 1.3
        dx_, dy_ = -(gw * 0.8 + i * 6) * P, -(gh * 0.55 - i * 3) * P
        s.css.add(f"@keyframes bat{i}{{0%{{transform:translate(0,0);opacity:0}}6%{{opacity:1}}"
                  f"50%{{transform:translate({dx_*0.5:.0f}px,{dy_*0.8:.0f}px)}}"
                  f"90%{{opacity:1}}100%{{transform:translate({dx_:.0f}px,{dy_:.0f}px);opacity:0}}}}"
                  f".bat{i}{{animation:bat{i} {dur:.1f}s steps({int(dur*8)}) infinite -{i*1.9:.1f}s}}")
        bx, by = x0 + (cx - 4) * P, y0 + (cy - 6) * P
        bmap = {"b": "black"}
        s.add(f'<g class="a bat{i}"><g class="a wA">{sprite_svg(BAT[0], bmap, P, bx, by)}</g>'
              f'<g class="a wB">{sprite_svg(BAT[1], bmap, P, bx, by)}</g></g>')
    s.add("</g>")


def pcb_scene(s, x0, y0, W, H, P=5):
    """A circuit board: an STM32, an IMU and a radio, with signals running along the traces."""
    gw, gh = W // P, H // P
    p = Pix(gw, gh)
    p.rect(0, 0, gw, gh, "#0e0e10")   # board: near-black with a few faint specks
    rnd = np.random.default_rng(17)
    for _ in range(60):
        p.set(rnd.integers(0, gw), rnd.integers(0, gh), "#141417")
    trace, pad = "#4a0a12", "#6a0a12"
    paths = [
        [(0, 4), (40, 4), (44, 8), (70, 8)],
        [(0, 18), (50, 18), (54, 14), (70, 14)],
        [(86, 9), (100, 9), (102, 11), (120, 11)],
        [(86, 13), (110, 13), (114, 17), (156, 17), (162, 11)],
        [(128, 10), (140, 10), (144, 6), (159, 6)],
        [(167, 7), (199, 7)],
        [(128, 13), (176, 13), (180, 17), (199, 17)],
    ]

    def cells(path):
        out = []
        for (ax, ay), (bx, by) in zip(path, path[1:]):
            n = max(abs(bx - ax), abs(by - ay))
            sx, sy = (bx > ax) - (bx < ax), (by > ay) - (by < ay)
            out += [(ax + i * sx, ay + i * sy) for i in range(n)]
        return out + [path[-1]]
    for path in paths:
        for (x, y) in cells(path):
            p.set(x, y, trace)
        for (x, y) in (path[0], path[-1]):
            p.set(x, y, pad)
    for i in range(6, 70, 9):      # vias
        p.set(i, 11, pad)

    def chip(x, y, w, h):
        p.rect(x, y, w, h, "#1c1c21")
        p.rect(x, y, w, 1, PX["steel"]); p.rect(x, y + h - 1, w, 1, PX["steel"])
        for i in range(x + 1, x + w - 1, 2):
            p.set(i, y - 1, PX["grey2"]); p.set(i, y + h, PX["grey2"])
    chip(70, 5, 16, 12)
    chip(120, 8, 8, 7)
    chip(159, 4, 8, 6)
    p.fade(l=0.25, r=0.06, t=0.12, b=0.12, seed=13)
    s.add(f'<g shape-rendering="crispEdges">{p.svg(P, x0, y0)}')
    for (cx, cy, txt) in ((78, 11.9, "STM32"), (124, 12.6, "IMU"), (163, 7.9, "RF")):
        s.text(x0 + cx * P, y0 + cy * P, txt, "mono", 9 if len(txt) > 3 else 8, 500, fill=C["muted"], ls=1, anchor="middle")
    # signals: each pulse steps along its trace one pixel at a time, with a short fading tail
    for k, path in enumerate(paths):
        cl = cells(path)
        n = len(cl) - 1
        dur = max(1.6, n * 0.045)
        frames = []
        for i, (x, y) in enumerate(cl):
            frames.append(f"{100*i/n:.2f}%{{transform:translate({(x-cl[0][0])*P}px,{(y-cl[0][1])*P}px)}}")
        s.css.add(f"@keyframes sig{k}{{{''.join(frames)}}}"
                  f".sig{k}{{animation:sig{k} {dur:.2f}s steps(1) infinite}}")
        for t, op in ((0, 1), (0.06, 0.5), (0.12, 0.22)):
            s.add(f'<rect class="a sig{k}" style="animation-delay:-{(k*0.37 + t) % dur:.2f}s" '
                  f'x="{x0+cl[0][0]*P}" y="{y0+cl[0][1]*P}" width="{P}" height="{P}" fill="{PX["red"]}" opacity="{op}"/>')
    s.css.add("@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:.1}}.blink{animation:blink 1.2s steps(1) infinite}")
    s.add(f'<rect class="a blink" x="{x0+88*P}" y="{y0+4*P}" width="{P}" height="{P}" fill="{PX["red"]}"/>')
    s.add(f'<rect x="{x0+90*P}" y="{y0+4*P}" width="{P}" height="{P}" fill="{PX["white"]}" opacity="0.8"/>')
    s.add("</g>")


SCENES = {"launch": launch_scene, "lidar": lidar_scene, "skyline": skyline_scene, "batcave": batcave_scene, "pcb": pcb_scene}


import numpy as np

# ---------------------------------------------------------------- ascii avatar scanner

RAMP = " .,:;-=+*#%@"


def ascii_scanner(s, cfg, x, y, cols=48, rows=18):
    av = cfg["avatar"]
    im = Image.open(os.path.join(HERE, "images", av["image"])).convert("L").crop(tuple(av["crop"]))
    im = im.resize((cols, rows), Image.BOX)
    g = (np.asarray(im) / 255.0) ** 0.8
    size, cw, lh = 10, 6.0, 10
    bw, bh = cols * cw + 24, rows * lh + 60
    s.add(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="8" fill="{C["panel"]}" fill-opacity="0.96" stroke="{C["edge"]}"/>')
    for (cx, cy, dx, dy) in [(x, y, 1, 1), (x + bw, y, -1, 1), (x, y + bh, 1, -1), (x + bw, y + bh, -1, -1)]:
        s.add(f'<path d="M{cx+dx*4} {cy+dy*18} V{cy+dy*4} H{cx+dx*18}" fill="none" stroke="{C["accent"]}" stroke-width="1.6"/>')
    s.text(x + 16, y + 22, av.get("label", "Scan_01 · avatar"), "mono", 10, 500, fill=C["muted"], ls=1.4, upper=True)
    s.text(x + bw - 16, y + 22, "Live", "mono", 10, 500, fill=C["accent"], ls=1.4, anchor="end", upper=True)
    s.add(f'<circle class="a rec" cx="{x+bw-52}" cy="{y+18.5}" r="3" fill="{C["accent"]}"/>')
    ax, ay = x + 12, y + 34
    colors = [(0.62, C["ink"]), (0.38, "#ff8a94"), (0.0, "#a50d18")]
    s.used.add(("mono", 400, "normal"))
    glitch_rows = {int(rows * 0.3): 0, int(rows * 0.5): 1, int(rows * 0.7): 2}
    lines = []
    for r in range(rows):
        spans, cur, run = [], None, ""
        for c in range(cols):
            v = g[r, c]
            ch = RAMP[min(len(RAMP) - 1, int(v * len(RAMP)))]
            col = next(cc for th, cc in colors if v >= th)
            if col != cur and run:
                spans.append(f'<tspan fill="{cur}">{escape(run)}</tspan>')
                run = ""
            cur = col
            run += ch
        spans.append(f'<tspan fill="{cur}">{escape(run)}</tspan>')
        t = (f'<text x="{ax}" y="{ay + (r+1)*lh - 2}" class="m" font-size="{size}" xml:space="preserve" '
             f'style="white-space:pre">{"".join(spans)}</text>')
        if r in glitch_rows:
            t = f'<g class="a gl{glitch_rows[r]}">{t}</g>'
        lines.append(t)
    s.defs.append(f'<clipPath id="reveal"><rect class="a rv" x="{ax-6}" y="{ay}" width="{cols*cw+12}" height="{rows*lh}" '
                  f'style="transform-origin:{ax}px {ay}px"/></clipPath>')
    s.defs.append('<filter id="glow" x="-10%" y="-200%" width="120%" height="500%"><feGaussianBlur stdDeviation="2.5"/></filter>')
    s.add(f'<g clip-path="url(#reveal)"><g class="a flick">{"".join(lines)}</g></g>')
    span = rows * lh
    s.add(f'<g class="a scan" style="--h:{span}px">'
          f'<rect x="{ax-4}" y="{ay-10}" width="{cols*cw+8}" height="12" fill="{C["accent"]}" opacity="0.10"/>'
          f'<rect x="{ax-4}" y="{ay}" width="{cols*cw+8}" height="2" fill="{C["accent"]}" opacity="0.9" filter="url(#glow)"/>'
          f'<rect x="{ax-4}" y="{ay}" width="{cols*cw+8}" height="1" fill="#ffd9dc"/></g>')
    s.text(x + 16, y + bh - 12, f"{cols} × {rows}  ·  {cfg['username']}", "mono", 10, fill=C["faint"], ls=1.2, upper=True)
    s.css.add(f"@keyframes rv{{from{{transform:scaleY(0)}}to{{transform:scaleY(1)}}}}"
              f".rv{{animation:rv 1.8s steps({rows}) both}}"
              f"@keyframes scan{{0%{{transform:translateY(0);opacity:1}}55%{{transform:translateY(var(--h));opacity:1}}"
              f"56%,100%{{transform:translateY(var(--h));opacity:0}}}}"
              f".scan{{animation:scan 4.2s linear infinite}}"
              "@keyframes flick{0%,90%,94%,100%{opacity:1}91%{opacity:.55}92%{opacity:.9}93%{opacity:.7}}"
              ".flick{animation:flick 5.3s linear infinite}"
              "@keyframes gl{0%,92%,100%{transform:translateX(0)}93%{transform:translateX(7px)}95%{transform:translateX(-4px)}96%{transform:translateX(0)}}"
              ".gl0{animation:gl 5.1s steps(1) infinite}.gl1{animation:gl 6.7s steps(1) infinite -2s}.gl2{animation:gl 7.9s steps(1) infinite -4s}"
              "@keyframes rec{50%{opacity:.2}}.rec{animation:rec 1.4s steps(1) infinite}")
    return bw, bh


# ---------------------------------------------------------------- hero, strips, projects

def hero(cfg):
    h = cfg["hero"]
    W, H = 1000, 530
    s = Svg(W, H, f'{cfg["name"]}. ' + " ".join(h["typing"]))
    s.panel()
    s.defs.append(f'<clipPath id="panel"><rect x="1" y="1" width="{W-2}" height="{H-2}" rx="12"/></clipPath>')
    s.add('<g clip-path="url(#panel)">')
    SCENES[h["scene"]](s, 0, 0, W, 290)
    s.add("</g>")
    ascii_scanner(s, cfg, 40, 250)
    x = 392
    s.text(x, 316, h["eyebrow"], "mono", 12, 500, fill=C["muted"], ls=2.2, upper=True)
    size = 54
    while sum(fnt("serif", 500, "italic" if it else "normal").width(t, size) for t, it in segments(h["name_line"])) > W - x - 36:
        size -= 2
    s.rich(x, 382, h["name_line"], size, 500)
    s.add(f'<line x1="{x}" x2="{W-40}" y1="414" y2="414" stroke="{C["edge"]}"/>')
    typer(s, x, 452, h["prompt"], h["typing"])
    s.text(x, 486, h["meta"], "mono", 10.5, fill=C["faint"], ls=1.4, upper=True)
    s.save("hero.svg")


def strip(name, num, title, spec, H=110):
    W = 1000
    s = Svg(W, H, f"{num} · {title}")
    SCENES[spec](s, 0, 0, W, H)
    label = f"{num}  ·  {title.upper()}"
    lw = fnt("mono", 500).width(label, 12, 1.4)
    s.add(f'<rect x="16" y="{H/2-16}" width="{lw+32:.1f}" height="32" rx="6" fill="{C["panel"]}" stroke="{C["edge"]}"/>')
    s.used.add(("mono", 500, "normal"))
    s.add(f'<text x="32" y="{H/2+4.5}" class="m" font-size="12" font-weight="500" letter-spacing="1.4" '
          f'fill="{C["muted"]}"><tspan fill="{C["accent"]}">{num}</tspan>  ·  {escape(title.upper())}</text>')
    s.save(name)


def project_card(cfg, p, i):
    W, H = 490, 176
    s = Svg(W, H, f'{p["name"]}: {p["blurb"]}')
    s.add(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="12" fill="{C["panel"]}" stroke="{C["edge"]}"/>')
    # a short red segment runs along the top edge now and then
    s.css.add("@keyframes run{0%{transform:translateX(0);opacity:0}8%{opacity:1}40%{transform:translateX(var(--d));opacity:1}"
              "46%,100%{transform:translateX(var(--d));opacity:0}}.run{animation:run 6s cubic-bezier(.45,0,.55,1) infinite}"
              "@keyframes nudge{0%,70%,100%{transform:translateX(0)}80%{transform:translateX(5px)}}"
              ".nudge{animation:nudge 4s ease-in-out infinite}")
    s.add(f'<rect class="a run" style="--d:{W-100}px;animation-delay:-{i*2.5}s" x="20" y="0" width="60" height="2" fill="{C["accent"]}"/>')
    s.text(24, 38, f"{i:02d}", "mono", 11.5, 500, fill=C["accent"], ls=1.2)
    x = W - 24
    for tag, col in reversed(p["tags"]):
        cw = fnt("mono", 500).width(tag.upper(), 10, 1) + 20
        x -= cw
        s.add(f'<rect x="{x:.1f}" y="22" width="{cw:.1f}" height="22" rx="11" fill="none" stroke="{C[col]}" stroke-opacity="0.65"/>')
        s.text(x + 10, 37, tag, "mono", 10, 500, fill=C[col], ls=1, upper=True)
        x -= 6
    s.text(24, 82, p["name"], "serif", 28, 500, fill=C["ink"], ls=-0.3)
    y = 110
    for line in wrap(p["blurb"], "serif", 15.5, W - 48)[:2]:
        s.text(24, y, line, "serif", 15.5, fill=C["ink2"])
        y += 23
    s.add(f'<line x1="24" x2="{W-24}" y1="{H-40}" y2="{H-40}" stroke="{C["edge"]}"/>')
    s.text(24, H - 16, fit(f'{cfg["username"]}/{p["repo"]}', "mono", 10.5, W - 150, ls=0.4), "mono", 10.5, fill=C["faint"], ls=0.4)
    s.used.add(("mono", 500, "normal"))
    s.add(f'<text class="m a nudge" style="animation-delay:-{i*0.7}s" x="{W-24}" y="{H-16}" font-size="11" font-weight="500" '
          f'letter-spacing="1.3" fill="{C["accent"]}" text-anchor="end">OPEN →</text>')
    s.save(f"project-{i}.svg")


def more_row(cfg):
    m = cfg["more"]
    W, H = 1000, 60
    s = Svg(W, H, "More projects: " + ", ".join(m["items"]))
    s.add(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="12" fill="none" stroke="{C["edge"]}" stroke-dasharray="4 4"/>')
    s.text(24, 34.5, "Also", "mono", 10.5, 500, fill=C["muted"], ls=1.6, upper=True)
    x = 76
    for it in m["items"]:
        cw = fnt("mono").width(it, 11.5) + 22
        s.add(f'<rect x="{x:.1f}" y="18" width="{cw:.1f}" height="24" rx="12" fill="{C["card"]}" stroke="{C["edge"]}"/>')
        s.text(x + 11, 34, it, "mono", 11.5, fill=C["ink2"])
        x += cw + 8
    s.css.add("@keyframes nudge{0%,70%,100%{transform:translateX(0)}80%{transform:translateX(5px)}}"
              ".nudge{animation:nudge 4s ease-in-out infinite}")
    s.used.add(("mono", 500, "normal"))
    s.add(f'<text class="m a nudge" x="{W-24}" y="34.5" font-size="11" font-weight="500" letter-spacing="1.3" '
          f'fill="{C["accent"]}" text-anchor="end">ALL REPOSITORIES →</text>')
    s.save("project-more.svg")


# ---------------------------------------------------------------- commit city

def fetch_calendar(login):
    req = urllib.request.Request(f"https://github.com/users/{login}/contributions",
                                 headers={"User-Agent": "profile-readme-builder"})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "replace")
    counts = {}
    for m in re.finditer(r'<tool-tip[^>]*for="(contribution-day-component-\d+-\d+)"[^>]*>([^<]*)</tool-tip>', html):
        n = re.match(r"(\d+)", m.group(2))
        counts[m.group(1)] = int(n.group(1)) if n else 0
    days = []
    for m in re.finditer(r'data-date="([\d-]+)"\s+id="(contribution-day-component-(\d+)-(\d+))"\s+data-level="(\d)"', html):
        date, cid, dow, wk, lvl = m.groups()
        days.append({"date": date, "dow": int(dow), "week": int(wk), "level": int(lvl), "count": counts.get(cid, 0)})
    if not days:
        raise SystemExit("Could not read the contribution calendar.")
    return days


CITY = ["#6a0a12", "#a50d18", "#e0101e", "#ff1f2d", "#f5f5f7"]


def shade(hexc, f):
    c = np.array([int(hexc[i:i + 2], 16) for i in (1, 3, 5)]) * f
    return "#%02x%02x%02x" % tuple(int(min(255, v)) for v in c)


def city(cfg, days):
    U, V = np.array([15.0, 5.0]), np.array([-14.0, 7.0])
    weeks = max(d["week"] for d in days) + 1
    peak = max(1, max(d["count"] for d in days))
    total = sum(d["count"] for d in days)
    best = max(days, key=lambda d: d["count"])
    maxh, W = 120, 1000
    ox = (W - (weeks * U[0] - 7 * V[0])) / 2 - 7 * V[0]
    oy = 40 + maxh
    H = int(oy + weeks * U[1] + 7 * V[1] + 60)
    s = Svg(W, H, f"Commit city: {total} contributions in the last year, one building per day.")
    s.panel()
    s.text(36, 44, "Commit city", "mono", 11, 500, fill=C["accent"], ls=1.6, upper=True)
    s.text(36, 66, f"{total:,} contributions in the last year. One building per day.", "serif", 15, style="italic", fill=C["ink2"])
    s.text(W - 36, 44, f"Tallest · {best['count']} on {best['date']}", "mono", 10.5, 500, fill=C["muted"], ls=1.2, anchor="end", upper=True)
    for i, col in enumerate(CITY):
        s.add(f'<rect x="{W-36-(5-i)*16}" y="56" width="10" height="10" fill="{col}"/>')
    O = np.array([ox, oy])
    pts = lambda arr: " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in arr)
    rnd = np.random.default_rng(3)
    s.css.add("@keyframes rise{from{transform:scaleY(0)}to{transform:scaleY(1)}}"
              ".rise{animation:rise .7s cubic-bezier(.2,.7,.2,1) both}"
              "@keyframes win{0%,100%{opacity:.15}50%{opacity:.95}}.win{animation:win 3s ease-in-out infinite}"
              "@keyframes glint{0%,100%{opacity:0}5%{opacity:.5}14%{opacity:0}}.glint{opacity:0;animation:glint 7s linear infinite}"
              "@keyframes drive{from{transform:translate(0,0)}to{transform:translate(var(--dx),var(--dy))}}"
              ".car{animation:drive linear infinite}")
    tiles = []
    for d in days:
        P = O + d["week"] * U + d["dow"] * V
        g = 0.12
        tiles.append((d, P + g * U + g * V, P + (1 - g) * U + g * V, P + (1 - g) * (U + V), P + g * U + (1 - g) * V))
    # ground first, then traffic in the streets, then buildings back to front
    for d, a, b, c, e in tiles:
        s.add(f'<polygon points="{pts([a, b, c, e])}" fill="#161618"/>')
    s.defs.append('<filter id="hl" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="1.6"/></filter>')
    span = weeks * U
    for street in (1, 3, 5, 7):
        for j in range(2):
            P0 = O + street * V - U
            dur = 11 + rnd.random() * 8
            col = "#f5f5f7" if (street + j) % 2 else C["accent"]
            s.add(f'<g class="a car" style="--dx:{span[0]+2*U[0]:.0f}px;--dy:{span[1]+2*U[1]:.0f}px;'
                  f'animation-duration:{dur:.1f}s;animation-delay:-{rnd.random()*dur:.1f}s">'
                  f'<circle cx="{P0[0]:.1f}" cy="{P0[1]:.1f}" r="3.2" fill="{col}" opacity="0.6" filter="url(#hl)"/>'
                  f'<circle cx="{P0[0]:.1f}" cy="{P0[1]:.1f}" r="1.4" fill="#fff4e0"/></g>')
    for d, a, b, c, e in sorted(tiles, key=lambda t: (t[0]["week"] + t[0]["dow"], t[0]["week"])):
        if d["count"] == 0:
            continue
        h = 6 + (maxh - 6) * (d["count"] / peak) ** 0.65
        col = CITY[4] if d["count"] == peak else CITY[min(3, max(0, d["level"] - 1))]
        up = np.array([0, -h])
        base_y, cx = (a[1] + c[1]) / 2, (a[0] + c[0]) / 2
        delay = 0.15 + d["week"] * 0.025 + d["dow"] * 0.01
        s.add(f'<g class="a rise" style="transform-origin:{cx:.1f}px {base_y:.1f}px;animation-delay:{delay:.2f}s">')
        s.add(f'<polygon points="{pts([b, c, c+up, b+up])}" fill="{shade(col, .72)}"/>')
        s.add(f'<polygon points="{pts([e, c, c+up, e+up])}" fill="{shade(col, .5)}"/>')
        s.add(f'<polygon points="{pts([a+up, b+up, c+up, e+up])}" fill="{shade(col, 1.1)}"/>')
        # a wave of light keeps rolling across the rooftops, west to east
        s.add(f'<polygon class="a glint" style="animation-delay:{d["week"]*0.06 + d["dow"]*0.03:.2f}s" '
              f'points="{pts([a+up, b+up, c+up, e+up])}" fill="#fff"/>')
        if h > 26:
            for wy in range(10, int(h) - 6, 9):
                for t in (0.3, 0.65):
                    q = b + (c - b) * t + np.array([0, -wy])
                    tw = rnd.random() < 0.3
                    cls = f' class="a win" style="animation-delay:-{rnd.random()*3:.1f}s"' if tw else ""
                    s.add(f'<rect{cls} x="{q[0]-1.2:.1f}" y="{q[1]-2:.1f}" width="2.4" height="3" fill="#ffd9dc" opacity="{0.8 if tw else 0.3}"/>')
        s.add("</g>")
    last = None
    for d in days:
        if d["dow"] == 0:
            m = d["date"][:7]
            if m != last and last is not None:
                P = O + d["week"] * U + 7.9 * V
                s.text(P[0], P[1] + 6, datetime.date.fromisoformat(d["date"]).strftime("%b"), "mono", 10, fill=C["muted"], ls=1, upper=True)
            last = m
    s.text(W - 36, H - 22, f"Rebuilt daily from github.com/{cfg['username']}", "mono", 10, fill=C["faint"], ls=1.2, anchor="end", upper=True)
    s.save("city.svg")


# ---------------------------------------------------------------- footer + readme

def footer(cfg):
    """A wordless closing scene."""
    W, H = 1000, 170
    s = Svg(W, H, "The Batcave: bats fly out of a cave past a red moon, server lights blinking inside.")
    s.panel(grid=False)
    s.defs.append(f'<clipPath id="panel"><rect x="1" y="1" width="{W-2}" height="{H-2}" rx="12"/></clipPath>')
    s.add('<g clip-path="url(#panel)">')
    SCENES[cfg["footer"]["scene"]](s, 0, 0, W, H)
    s.add("</g>")
    s.save("footer.svg")


def readme(cfg):
    n, u = cfg["name"], cfg["username"]
    cards = "\n".join(
        f'<a href="https://github.com/{u}/{p["repo"]}"><img src="assets/project-{i}.svg" width="49%" '
        f'alt="{escape(p["name"])}: {escape(p["blurb"])}"></a>' for i, p in enumerate(cfg["projects"], 1))
    stack_alt = "; ".join(g["label"] + ": " + ", ".join(g["items"]) for g in cfg["stack"])
    return f"""<!-- Generated by build/build.py from build/profile.json. Edit those, not this file. -->

<img src="assets/hero.svg" width="100%" alt="{escape(n)}. Currently building: {escape(', '.join(cfg['hero']['typing']))}.">

<img src="assets/strip-01.svg" width="100%" alt="01 · Projects">

<p align="center">
{cards}
</p>

<a href="https://github.com/{u}?tab=repositories"><img src="assets/project-more.svg" width="100%" alt="Also: {escape(', '.join(cfg['more']['items']))}. All repositories."></a>

<img src="assets/strip-02.svg" width="100%" alt="02 · Commit city">

<img src="assets/city.svg" width="100%" alt="Commit city: my contribution graph as an isometric city, one building per day, rebuilt daily">

<img src="assets/stack.svg" width="100%" alt="Toolbox: {escape(stack_alt)}">
"""


def preview(md):
    html = re.sub(r"<!--.*?-->", "", md, flags=re.S).replace('src="assets/', 'src="../assets/')
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Profile preview</title><style>
body{{margin:0;font:14px -apple-system,Segoe UI,sans-serif;background:#0d1117;color:#e6edf3}}
.bar{{position:sticky;top:0;z-index:1;padding:10px 16px;background:#0d1117;border-bottom:1px solid #3d444d}}
.box{{max-width:880px;margin:24px auto;border:1px solid #3d444d;border-radius:6px;padding:24px 32px}}
.box p{{margin:0 0 16px}} .box img{{max-width:100%;vertical-align:middle}} .box>img,.box>a>img{{display:block;margin:0 0 16px}}
</style></head><body><div class="bar">preview / README.md</div><div class="box">{html}</div></body></html>"""


def main():
    with open(os.path.join(HERE, "profile.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    if "--city" in sys.argv:
        city(cfg, fetch_calendar(cfg["username"]))
        return
    print("Building assets:")
    for name in os.listdir(ASSETS) if os.path.isdir(ASSETS) else []:
        os.remove(os.path.join(ASSETS, name))
    hero(cfg)
    st = cfg["strips"]
    strip("strip-01.svg", "01", "Projects", st[0])
    strip("strip-02.svg", "02", "Commit city", st[1])
    for i, p in enumerate(cfg["projects"], 1):
        project_card(cfg, p, i)
    more_row(cfg)
    city(cfg, fetch_calendar(cfg["username"]))
    stack(cfg)
    md = readme(cfg)
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    with open(os.path.join(HERE, "preview.html"), "w", encoding="utf-8") as fh:
        fh.write(preview(md))
    print("  README.md and build/preview.html written")


if __name__ == "__main__":
    main()

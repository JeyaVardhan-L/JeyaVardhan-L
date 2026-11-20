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
    # night paper with a warm cast, light ink, and one red accent
    "panel": "#100c0d", "card": "#171112", "edge": "#2e2224",
    "ink": "#f3eded", "ink2": "#c7b9ba", "muted": "#917f81", "faint": "#5d4c4e",
    "accent": "#ff5a5f", "accent2": "#ff8a8e", "grid": "rgba(255,90,95,0.05)",
    # tag colours, all warm so the page stays red without being one flat colour
    "red": "#ff5a5f", "coral": "#ff8f6b", "amber": "#f5b452", "rose": "#f07aa4", "sand": "#e7c9a0",
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
        s.add(f'<rect x="{x:.1f}" y="20" width="4" height="4" fill="#3a2b2e"/>')
        x += 9
    x = W - 6
    while x >= right_start:
        s.add(f'<rect x="{x:.1f}" y="20" width="4" height="4" fill="#3a2b2e"/>')
        x -= 9
    s.used.add(("mono", 500, "normal"))
    s.add(f'<text x="500" y="26.5" class="m" font-size="12" font-weight="500" letter-spacing="1.4" '
          f'text-anchor="middle" fill="{C["muted"]}"><tspan fill="{C["accent"]}">{num}</tspan>'
          f'  ·  {escape(title.upper())}</text>')
    s.save(f"divider-{num}.svg")


def stack(cfg):
    W, x0, x1 = 1000, 190, 964
    rows, y = [], 40
    for g in cfg["stack"]:
        chips, x, ry = [], x0, y
        for it in g["items"]:
            cw = fnt("mono").width(it, 13) + 40
            if x + cw > x1:
                x, ry = x0, ry + 42
            chips.append((x, ry, cw, it))
            x += cw + 10
        rows.append((g, y, chips))
        y = ry + 50
    H = int(y + 34)
    s = Svg(W, H, "Toolbox. " + ". ".join(f'{g["label"]}: {", ".join(g["items"])}' for g in cfg["stack"]))
    s.panel()
    for g, gy, chips in rows:
        col = C[g["color"]]
        s.text(36, gy + 20, g["label"], "mono", 11, 500, fill=C["muted"], ls=1.4, upper=True)
        for cx, cy, cw, it in chips:
            s.add(f'<rect x="{cx}" y="{cy}" width="{cw:.1f}" height="30" rx="15" fill="{C["card"]}" stroke="{col}" stroke-opacity="0.75"/>')
            s.add(f'<rect x="{cx+14}" y="{cy+12}" width="6" height="6" fill="{col}"/>')
            s.text(cx + 28, cy + 20, it, "mono", 13, fill=C["ink"])
    if cfg.get("stack_note"):
        s.text(W - 36, H - 20, cfg["stack_note"], "serif", 14, style="italic", fill=C["muted"], anchor="end")
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



# ---------------------------------------------------------------- scenes
# A painting is shown at its full resolution (sharpened a little, never upscaled in the file),
# and parts of it move: water ripples and sparkles, leaves sway, clouds drift. Only its edges
# break into small crisp blocks, an ordered-plus-noise dither, so it sinks into the dark panel.

import numpy as np
from PIL import ImageEnhance

BAYER = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) + 0.5) / 16

EFFECTS = {
    # kind: (turbulence baseFrequency from, to, displacement scale, seconds)
    "water": ("0.006 0.10", "0.008 0.13", 3.2, 5),
    "leaves": ("0.03 0.04", "0.036 0.046", 2.6, 4),
}


def to_uri(im, quality=92):
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True, subsampling=0)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def dissolve_mask(gw, gh, fade, seed=7):
    xs, ys = np.meshgrid(np.arange(gw) + 0.5, np.arange(gh) + 0.5)
    l, r, t, b = fade
    k = np.ones((gh, gw))
    if l: k = np.minimum(k, xs / (l * gw))
    if r: k = np.minimum(k, (gw - xs) / (r * gw))
    if t: k = np.minimum(k, ys / (t * gh))
    if b: k = np.minimum(k, (gh - ys) / (b * gh))
    k = np.clip(k, 0, 1)
    k = k * k * (3 - 2 * k)
    noise = np.random.default_rng(seed).random((gh, gw))
    th = 0.45 * BAYER[np.arange(gh)[:, None] % 4, np.arange(gw)[None, :] % 4] + 0.55 * noise
    m = Image.fromarray(((k > th) * 255).astype(np.uint8), "L")
    buf = io.BytesIO()
    m.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def scene(s, sid, spec, x, y, w, h, fade=(0.06, 0.06, 0.0, 0.42), block=4):
    im = Image.open(os.path.join(HERE, "images", spec["image"])).convert("RGB")
    W0, H0 = im.size
    cx0, cy0, cx1, cy1 = spec["crop"]
    im = im.crop((round(cx0 * W0), round(cy0 * H0), round(cx1 * W0), round(cy1 * H0)))
    im = ImageEnhance.Sharpness(im).enhance(1.35)
    im = ImageEnhance.Contrast(im).enhance(1.05)
    iw, ih = im.size
    sc = max(w / iw, h / ih)
    dw, dh = iw * sc, ih * sc
    dx, dy = x + (w - dw) / 2, y + (h - dh) / 2
    uri = to_uri(im)

    def region(r):
        a, b, c, d = r
        X = lambda v: dx + np.clip((v - cx0) / (cx1 - cx0), 0, 1) * dw
        Y = lambda v: dy + np.clip((v - cy0) / (cy1 - cy0), 0, 1) * dh
        return X(a), Y(b), X(c) - X(a), Y(d) - Y(b)

    gw, gh = int(np.ceil(w / block)), int(np.ceil(h / block))
    s.defs.append(f'<image id="{sid}" href="{uri}" xlink:href="{uri}" x="{dx:.1f}" y="{dy:.1f}" '
                  f'width="{dw:.1f}" height="{dh:.1f}" preserveAspectRatio="none"/>')
    mask = dissolve_mask(gw, gh, fade, seed=len(sid) * 13)
    s.defs.append(f'<mask id="{sid}-dis" maskUnits="userSpaceOnUse" x="{x}" y="{y}" width="{w}" height="{h}">'
                  f'<image href="{mask}" xlink:href="{mask}" x="{x}" y="{y}" width="{gw*block}" height="{gh*block}" '
                  f'preserveAspectRatio="none" image-rendering="optimizeSpeed" style="image-rendering:pixelated"/></mask>')
    s.defs.append(f'<clipPath id="{sid}-c"><rect x="{x}" y="{y}" width="{w}" height="{h}"/></clipPath>')
    if "feather" not in s.css:
        s.defs.append('<filter id="feather" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="5"/></filter>')
        s.css.add("feather")
    s.css.add("@keyframes drift{from{transform:translateX(-6px)}to{transform:translateX(8px)}}"
              ".drift{animation:drift 16s ease-in-out infinite alternate}"
              "@keyframes spark{0%,100%{opacity:0}45%{opacity:0}50%{opacity:1}58%{opacity:0}}"
              ".spark{animation:spark 3s linear infinite}")
    s.add(f'<g mask="url(#{sid}-dis)"><g clip-path="url(#{sid}-c)"><use href="#{sid}" xlink:href="#{sid}"/>')
    rnd = np.random.default_rng(len(sid))
    for i, (kind, r) in enumerate(spec.get("motion", [])):
        rx, ry, rw, rh = region(r)
        if rw < 2 or rh < 2:
            continue
        mid = f"{sid}-m{i}"
        s.defs.append(f'<mask id="{mid}" maskUnits="userSpaceOnUse" x="{x}" y="{y}" width="{w}" height="{h}">'
                      f'<rect x="{rx+6:.1f}" y="{ry+6:.1f}" width="{max(rw-12, 1):.1f}" height="{max(rh-12, 1):.1f}" '
                      f'fill="#fff" filter="url(#feather)"/></mask>')
        if kind == "drift":
            s.add(f'<g mask="url(#{mid})"><g class="a drift" style="animation-delay:-{i*3}s">'
                  f'<use href="#{sid}" xlink:href="#{sid}"/></g></g>')
            continue
        f0, f1, scale, dur = EFFECTS[kind]
        fid = f"{mid}-f"
        s.defs.append(
            f'<filter id="{fid}" filterUnits="userSpaceOnUse" x="{rx-8:.1f}" y="{ry-8:.1f}" width="{rw+16:.1f}" height="{rh+16:.1f}">'
            f'<feTurbulence type="turbulence" baseFrequency="{f0}" numOctaves="2" seed="{4+i}" result="n">'
            f'<animate attributeName="baseFrequency" dur="{dur}s" values="{f0};{f1};{f0}" repeatCount="indefinite"/>'
            f'</feTurbulence><feDisplacementMap in="SourceGraphic" in2="n" scale="{scale}" '
            f'xChannelSelector="R" yChannelSelector="G"/></filter>')
        s.add(f'<g mask="url(#{mid})"><use href="#{sid}" xlink:href="#{sid}" filter="url(#{fid})"/></g>')
        if kind == "water":   # sun glints on the water
            for _ in range(int(rw * rh / 1800)):
                px, py = rx + rnd.random() * rw, ry + rh * (0.15 + 0.8 * rnd.random())
                s.add(f'<rect class="a spark" style="animation-delay:-{rnd.random()*3:.2f}s;animation-duration:{2.4+rnd.random()*2:.1f}s" '
                      f'x="{px:.1f}" y="{py:.1f}" width="{2+rnd.random()*3:.1f}" height="1.2" fill="#fff8ec"/>')
    # pixels darken as they break apart, so the edge melts into the panel instead of sparkling
    l, r, t, b = fade
    for side, frac in (("l", l), ("r", r), ("t", t), ("b", b)):
        if not frac:
            continue
        gid = f"{sid}-g{side}"
        x1, y1, x2, y2 = {"l": (1, 0, 0, 0), "r": (0, 0, 1, 0), "t": (0, 1, 0, 0), "b": (0, 0, 0, 1)}[side]
        s.defs.append(f'<linearGradient id="{gid}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">'
                      f'<stop offset="0" stop-color="{C["panel"]}" stop-opacity="0"/>'
                      f'<stop offset="1" stop-color="{C["panel"]}" stop-opacity="0.92"/></linearGradient>')
        if side in "lr":
            gw_ = w * frac
            gx = x if side == "l" else x + w - gw_
            s.add(f'<rect x="{gx:.1f}" y="{y}" width="{gw_:.1f}" height="{h}" fill="url(#{gid})"/>')
        else:
            gh_ = h * frac
            gy = y if side == "t" else y + h - gh_
            s.add(f'<rect x="{x}" y="{gy:.1f}" width="{w}" height="{gh_:.1f}" fill="url(#{gid})"/>')
    s.add("</g></g>")


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
    colors = [(0.62, C["ink"]), (0.38, "#ffb9bb"), (0.0, "#b5404a")]
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
          f'<rect x="{ax-4}" y="{ay}" width="{cols*cw+8}" height="1" fill="#ffe1e2"/></g>')
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
    scene(s, "sky", h["scene"], 0, 0, W, 290, fade=(0.05, 0.05, 0.0, 0.36))
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
    scene(s, "st", spec, 0, 0, W, H, fade=(0.3, 0.1, 0.14, 0.14))
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


CITY = ["#7a2530", "#b8323f", "#ff5a5f", "#ff8f6b", "#ffd27a"]


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
        s.add(f'<polygon points="{pts([a, b, c, e])}" fill="#1e1517"/>')
    s.defs.append('<filter id="hl" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="1.6"/></filter>')
    span = weeks * U
    for street in (1, 3, 5, 7):
        for j in range(2):
            P0 = O + street * V - U
            dur = 11 + rnd.random() * 8
            col = "#ffd27a" if (street + j) % 2 else C["accent"]
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
                    s.add(f'<rect{cls} x="{q[0]-1.2:.1f}" y="{q[1]-2:.1f}" width="2.4" height="3" fill="#ffe2b0" opacity="{0.8 if tw else 0.3}"/>')
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
    f = cfg["footer"]
    W, H = 1000, 200
    s = Svg(W, H, f["title"].replace("*", ""))
    s.panel(grid=False)
    s.defs.append(f'<clipPath id="panel"><rect x="1" y="1" width="{W-2}" height="{H-2}" rx="12"/></clipPath>')
    s.add('<g clip-path="url(#panel)">')
    scene(s, "ft", f["scene"], 400, 0, 600, H, fade=(0.42, 0.0, 0.08, 0.08))
    s.add("</g>")
    s.text(48, 84, f["eyebrow"], "mono", 11, 500, fill=C["accent"], ls=1.8, upper=True)
    s.rich(48, 128, f["title"], 34, 500)
    s.text(48, 160, f["text"], "serif", 16, fill=C["ink2"])
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

<img src="assets/divider-03.svg" width="100%" alt="03 · Toolbox">

<img src="assets/stack.svg" width="100%" alt="Toolbox: {escape(stack_alt)}">

<img src="assets/footer.svg" width="100%" alt="{escape(cfg['footer']['title'].replace('*', ''))}">
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
    divider("03", "Toolbox")
    for i, p in enumerate(cfg["projects"], 1):
        project_card(cfg, p, i)
    more_row(cfg)
    city(cfg, fetch_calendar(cfg["username"]))
    stack(cfg)
    footer(cfg)
    md = readme(cfg)
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    with open(os.path.join(HERE, "preview.html"), "w", encoding="utf-8") as fh:
        fh.write(preview(md))
    print("  README.md and build/preview.html written")


if __name__ == "__main__":
    main()

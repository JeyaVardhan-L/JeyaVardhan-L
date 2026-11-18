#!/usr/bin/env python3
"""Builds the profile README and its SVG cards from profile.json.

    python build/build.py            # everything (numbers card from the GitHub API if GITHUB_TOKEN is set)
    python build/build.py --numbers  # only the numbers card (what the daily workflow runs)
    python build/build.py --demo     # numbers card with made-up data, for previewing the look

GitHub strips CSS and fonts from READMEs, so every styled block is an SVG image.
Fonts are subset and embedded inside each SVG, so they render the same for every visitor.
"""
import base64, datetime, io, json, os, random, re, sys, urllib.request
from xml.sax.saxutils import escape
from fontTools.ttLib import TTFont
from fontTools import subset
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")

C = {
    "paper": "#fafafa", "card": "#ffffff", "ink": "#111113", "ink2": "#3b3b40",
    "muted": "#8a8a92", "faint": "#b9b9c0", "rule": "#e4e4e8", "rule2": "#efeff2",
    "blue": "#2b4cf2", "blue2": "#5a74ff", "blue_soft": "#a9b7ff",
    "wash": "rgba(43,76,242,0.09)", "grid": "rgba(43,76,242,0.075)",
    # colours taken from the paintings: sea, roof tiles, grass, sun
    "sea": "#1f7f95", "roof": "#c8622e", "grass": "#4f8f3a", "sun": "#c99a1e",
    "amber": "#a86b00",
}
LANG_COLORS = ["blue", "sea", "roof", "grass", "sun"]

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
        self.key = key
        self.path = os.path.join(HERE, "fonts", FONT_FILES[key])
        tt = TTFont(self.path)
        self.upm = tt["head"].unitsPerEm
        self.cmap = tt.getBestCmap()
        self.hmtx = tt["hmtx"].metrics
        self._b64 = None

    def width(self, text, size, ls=0.0):
        units = 0
        for ch in text:
            g = self.cmap.get(ord(ch)) or self.cmap.get(ord("?"))
            units += self.hmtx[g][0]
        return units * size / self.upm + ls * len(text)

    def b64(self):
        if self._b64 is None:
            opts = subset.Options()
            opts.flavor = "woff"
            opts.layout_features = ["kern", "liga", "onum", "pnum"]
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
    f = fnt(fam, weight)
    for w in words:
        trial = (cur + " " + w).strip()
        if f.width(trial, size, ls) <= maxw or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def segments(text):
    """'a *b* c' -> [('a ', False), ('b', True), (' c', False)]"""
    out = []
    for i, part in enumerate(re.split(r"\*", text)):
        if part:
            out.append((part, i % 2 == 1))
    return out


def rich_width(text, size, weight=400):
    return sum(fnt("serif", weight, "italic" if it else "normal").width(s, size) for s, it in segments(text))


def image_uri(name, max_w=1000, quality=86):
    im = Image.open(os.path.join(HERE, "images", name)).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------- svg writer

class Svg:
    def __init__(self, w, h, label):
        self.w, self.h, self.label = w, h, label
        self.parts, self.defs, self.css, self.used = [], [], [], set()

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, fam="serif", size=16, weight=400, style="normal", fill=C["ink"],
             anchor="start", ls=0.0, upper=False, opacity=None, cls=""):
        self.used.add((fam, weight, style))
        if upper:
            s = s.upper()
        attrs = f'x="{x:.1f}" y="{y:.1f}" class="{fam[0]} {cls}" font-size="{size}" fill="{fill}"'
        if weight != 400:
            attrs += f' font-weight="{weight}"'
        if style != "normal":
            attrs += f' font-style="{style}"'
        if anchor != "start":
            attrs += f' text-anchor="{anchor}"'
        if ls:
            attrs += f' letter-spacing="{ls}"'
        if opacity is not None:
            attrs += f' opacity="{opacity}"'
        self.add(f"<text {attrs}>{escape(s)}</text>")

    def rich(self, x, y, s, size, weight=500, fill=C["ink"], accent=C["blue"], anchor="start"):
        """Serif line where *words* are italic and take the accent colour."""
        spans = []
        for part, it in segments(s):
            self.used.add(("serif", weight, "italic" if it else "normal"))
            if it:
                spans.append(f'<tspan font-style="italic" fill="{accent}">{escape(part)}</tspan>')
            else:
                spans.append(escape(part))
        a = f' text-anchor="{anchor}"' if anchor != "start" else ""
        self.add(f'<text x="{x}" y="{y}" class="s" font-size="{size}" font-weight="{weight}" '
                 f'fill="{fill}" letter-spacing="-0.01em"{a}>{"".join(spans)}</text>')

    def grid_pattern(self):
        self.defs.append(
            f'<pattern id="grid" width="16" height="16" patternUnits="userSpaceOnUse">'
            f'<path d="M16 0H0V16" fill="none" stroke="{C["grid"]}" stroke-width="1"/></pattern>')

    def card(self, r=8):
        self.add(f'<rect x="0.5" y="0.5" width="{self.w-1}" height="{self.h-1}" rx="{r}" '
                 f'fill="{C["paper"]}" stroke="{C["rule"]}"/>')

    def plate(self, href, x, y, w, h, r=5, cid="plate", align="xMidYMid"):
        self.defs.append(f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}"/></clipPath>')
        self.add(f'<image href="{href}" x="{x}" y="{y}" width="{w}" height="{h}" '
                 f'preserveAspectRatio="{align} slice" clip-path="url(#{cid})"/>')
        self.add(f'<rect x="{x+.5}" y="{y+.5}" width="{w-1}" height="{h-1}" rx="{r}" fill="none" '
                 f'stroke="rgba(17,17,19,0.08)"/>')

    def render(self):
        faces = []
        for (fam, weight, style) in sorted(self.used):
            name = "FSerif" if fam == "serif" else "FMono"
            faces.append(f"@font-face{{font-family:{name};font-weight:{weight};font-style:{style};"
                         f"src:url(data:font/woff;base64,{fnt(fam, weight, style).b64()}) format('woff')}}")
        css = "\n".join(faces + [
            f".s{{font-family:{FAMILY['serif']};font-optical-sizing:auto;text-rendering:optimizeLegibility}}",
            f".m{{font-family:{FAMILY['mono']};font-variant-ligatures:none;font-feature-settings:'liga' 0,'calt' 0}}",
        ] + self.css)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{escape(self.label)}">'
                f"<title>{escape(self.label)}</title><style>{css}</style>"
                f"<defs>{''.join(self.defs)}</defs>{''.join(self.parts)}</svg>")

    def save(self, name):
        os.makedirs(ASSETS, exist_ok=True)
        with open(os.path.join(ASSETS, name), "w", encoding="utf-8") as fh:
            fh.write(self.render())
        print(f"  assets/{name:<22} {os.path.getsize(os.path.join(ASSETS, name)) // 1024:>4} KB")


# ---------------------------------------------------------------- cards

def hero(cfg):
    h = cfg["hero"]
    W, H = 1000, 460
    s = Svg(W, H, f'{cfg["name"]}. {h["title"].replace("*", "")} {h["lede"]}')
    s.plate(image_uri(h["image"]), 0, 0, W, H, r=10, cid="hero", align="xMidYMid")
    s.text(500, 84, h["eyebrow"], "mono", 13, 500, fill="#ffffff", anchor="middle", ls=2.4, upper=True, opacity=0.92)
    size = 56
    while rich_width(h["title"], size) > 700:
        size -= 2
    s.rich(500, 150, h["title"], size, 500, fill="#ffffff", accent="#ffe9b0", anchor="middle")
    s.text(500, 194, h["lede"], "serif", 20, fill="#ffffff", anchor="middle", opacity=0.94)
    s.save("hero.svg")


def divider(num, title):
    W, H = 1000, 44
    label = f"{num}  ·  {title.upper()}"
    lw = fnt("mono", 500).width(label, 12, 1.4)
    s = Svg(W, H, f"{num} · {title}")
    gap, step, sq = 20, 9, 4
    left_end, right_start = W / 2 - lw / 2 - gap, W / 2 + lw / 2 + gap
    x = 2.0
    while x + sq <= left_end:
        s.add(f'<rect x="{x:.1f}" y="20" width="{sq}" height="{sq}" fill="#cdcdd4"/>')
        x += step
    x = W - 2 - sq
    while x >= right_start:
        s.add(f'<rect x="{x:.1f}" y="20" width="{sq}" height="{sq}" fill="#cdcdd4"/>')
        x -= step
    s.used.add(("mono", 500, "normal"))
    s.add(f'<text x="500" y="26.5" class="m" font-size="12" font-weight="500" letter-spacing="1.4" '
          f'text-anchor="middle" fill="{C["muted"]}"><tspan fill="{C["blue2"]}">{num}</tspan>'
          f'  ·  {escape(title.upper())}</text>')
    s.save(f"divider-{num}.svg")


def about(cfg):
    W, pad, cx = 1000, 36, 118
    cw = W - cx - 44
    layout, y = [], 30
    for i, pair in enumerate(cfg["about"]):
        q = wrap(pair["q"].upper(), "mono", 13, cw, 500, 1.2)
        a = wrap(pair["a"], "serif", 19, cw)
        layout.append((y, q, a))
        y += 28 + len(q) * 22 + 22 + len(a) * 31 + 16
        if i < len(cfg["about"]) - 1:
            y += 26
    H = int(y + 12)
    label = " ".join(f'IN: {p["q"]} OUT: {p["a"]}' for p in cfg["about"])
    s = Svg(W, H, label)
    s.card()
    for i, (y0, q, a) in enumerate(layout):
        yy = y0 + 28
        s.text(pad, yy, "IN:", "mono", 12, 500, fill=C["muted"], ls=1.2)
        for line in q:
            s.text(cx, yy, line, "mono", 13, 500, fill=C["ink"], ls=1.2)
            yy += 22
        s.add(f'<line x1="{pad}" x2="{W-pad}" y1="{yy-6}" y2="{yy-6}" stroke="{C["rule"]}"/>')
        yy += 26
        s.text(pad, yy - 1, "OUT:", "mono", 12, 500, fill=C["blue"], ls=1.2)
        for line in a:
            s.text(cx, yy, line, "serif", 19, fill=C["ink"])
            yy += 31
        if i < len(layout) - 1:
            s.add(f'<rect x="{pad}" y="{yy+8}" width="{W-2*pad}" height="1" fill="{C["rule"]}"/>')
            s.add(f'<rect x="{pad}" y="{yy+11}" width="{W-2*pad}" height="1" fill="{C["rule"]}"/>')
    s.save("about.svg")


# ---------------------------------------------------------------- project figures
# Each project gets a small animated line-art figure on graph paper, in the field-guide
# vocabulary: blue strokes, white boxes, mono labels. Pick one with "art" in profile.json,
# or give "media": "file.gif" (in build/images) to use your own animated image instead.

ANIM_BASE = ("*{transform-box:view-box}"
             "@media (prefers-reduced-motion:reduce){.a{animation:none!important}}")
LINE = f'stroke="{C["blue"]}" stroke-width="1.4" fill="none"'
BOX = f'fill="{C["card"]}" stroke="{C["blue"]}" stroke-width="1.4"'


def arrow(s, x1, y, x2):
    s.add(f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" {LINE}/>')
    s.add(f'<path d="M{x2-6} {y-4} L{x2} {y} L{x2-6} {y+4}" {LINE}/>')


def art_shell(s, p, x, y, w, h):
    """A pipeline: data moves from ls through grep to wc, one packet at a time."""
    cmd = p.get("art_text", "$ ls | grep .c | wc -l")
    s.text(x + 20, y + 32, cmd, "mono", 12.5, fill=C["ink"])
    cw = fnt("mono").width(cmd, 12.5)
    s.add(f'<rect class="a cur" x="{x+24+cw:.1f}" y="{y+21}" width="7" height="14" fill="{C["blue"]}"/>')
    names = [part.strip() for part in cmd.lstrip("$ ").split("|")][:3]
    bw, gap = 104, 46
    bx0 = x + (w - (3 * bw + 2 * gap)) / 2
    by = y + 78
    # packets travel under the boxes, so they look like they pass through them
    for i in range(3):
        s.add(f'<rect class="a pk" style="animation-delay:{i*1.2}s" x="{bx0+bw-4:.1f}" y="{by+16}" '
              f'width="8" height="8" rx="1" fill="{C["blue"]}"/>')
    for i, name in enumerate(names):
        bx = bx0 + i * (bw + gap)
        s.text(bx, by - 10, f"0{i+1}", "mono", 10.5, 500, fill=C["muted"], ls=1.2)
        s.add(f'<rect x="{bx:.1f}" y="{by}" width="{bw}" height="40" rx="4" {BOX}/>')
        s.add(f'<rect class="a lit" style="animation-delay:{i*1.2}s" x="{bx:.1f}" y="{by}" width="{bw}" '
              f'height="40" rx="4" fill="{C["wash"]}"/>')
        s.text(bx + bw / 2, by + 25, name, "mono", 12.5, 500, fill=C["ink"], anchor="middle")
        if i < 2:
            arrow(s, bx + bw + 6, by + 20, bx + bw + gap - 6)
    s.text(x + w / 2, by + 68, "stdout  →  pipe  →  stdin", "mono", 10.5, fill=C["muted"], ls=1.2, anchor="middle", upper=True)
    s.text(x + w - 20, y + h - 16, p.get("art_out", "→ 14"), "mono", 12.5, 500, fill=C["blue"], anchor="end")
    travel = 2 * (bw + gap)
    s.css.append(
        ANIM_BASE +
        ".cur{animation:blink 1.1s steps(1) infinite}@keyframes blink{50%{opacity:0}}"
        f".pk{{opacity:0;animation:flow 3.6s linear infinite}}"
        f"@keyframes flow{{0%{{opacity:0;transform:translateX(0)}}6%{{opacity:1}}"
        f"30%{{opacity:1;transform:translateX({travel/2:.0f}px)}}36%,100%{{opacity:0;transform:translateX({travel/2:.0f}px)}}}}"
        ".lit{opacity:0;animation:lit 3.6s ease-in-out infinite}"
        "@keyframes lit{0%,100%{opacity:0}15%{opacity:1}35%{opacity:0}}")


def art_rocket(s, p, x, y, w, h):
    """Thrust vector control: the body drifts, the motor tilts the other way to bring it back."""
    cx, gy = x + w / 2, y + 136          # gimbal point
    s.add(f'<line x1="{cx}" y1="{y+12}" x2="{cx}" y2="{y+h-10}" stroke="{C["blue_soft"]}" '
          f'stroke-width="1" stroke-dasharray="2 4"/>')
    s.add(f'<g class="a body" style="transform-origin:{cx}px {gy}px">')
    s.add(f'<path d="M{cx} {y+18} C{cx+12} {y+32} {cx+16} {y+44} {cx+16} {y+56} L{cx-16} {y+56} '
          f'C{cx-16} {y+44} {cx-12} {y+32} {cx} {y+18} Z" {BOX}/>')
    s.add(f'<rect x="{cx-16}" y="{y+56}" width="32" height="{gy-y-56}" {BOX}/>')
    s.add(f'<line x1="{cx-16}" x2="{cx+16}" y1="{y+84}" y2="{y+84}" {LINE}/>')
    s.add(f'<rect x="{cx-16}" y="{y+84}" width="32" height="14" fill="{C["wash"]}"/>')
    for d in (-1, 1):
        s.add(f'<path d="M{cx+16*d} {gy-24} L{cx+32*d} {gy+2} L{cx+16*d} {gy-4}" {BOX}/>')
    s.add(f'<g class="a noz" style="transform-origin:{cx}px {gy}px">')
    s.add(f'<path d="M{cx-7} {gy} L{cx+7} {gy} L{cx+10} {gy+14} L{cx-10} {gy+14} Z" {BOX}/>')
    for i, dx in enumerate((-5, 0, 5)):
        s.add(f'<line class="a fl" style="animation-delay:{i*0.13}s" x1="{cx+dx}" y1="{gy+19}" '
              f'x2="{cx+dx*1.6}" y2="{gy+19+(30 if dx == 0 else 20)}" stroke="{C["roof"]}" '
              f'stroke-width="1.4" stroke-dasharray="4 4"/>')
    s.add("</g></g>")
    s.add(f'<circle cx="{cx}" cy="{gy}" r="2.5" fill="{C["blue"]}"/>')
    steps = ["IMU reads tilt", "PID decides", "Servo tilts motor"]
    for i, t in enumerate(steps):
        s.text(x + 20, y + 40 + i * 24, f"0{i+1}", "mono", 10.5, 500, fill=C["faint"], ls=1.2)
        s.text(x + 44, y + 40 + i * 24, t, "mono", 10.5, 500, fill=C["muted"], ls=1.2, upper=True,
               cls=f"a st st{i}")
    s.add(f'<line x1="{cx+18}" y1="{gy+8}" x2="{x+w-110}" y2="{gy+8}" stroke="{C["blue_soft"]}" '
          f'stroke-width="1" stroke-dasharray="2 4"/>')
    s.text(x + w - 20, gy + 12, p.get("art_text", "Gimbal ±8°"), "mono", 10.5, 500, fill=C["blue"],
           ls=1.2, anchor="end", upper=True)
    s.css.append(
        ANIM_BASE +
        ".body{animation:sway 4s ease-in-out infinite alternate}@keyframes sway{from{transform:rotate(-3deg)}to{transform:rotate(3deg)}}"
        ".noz{animation:gim 4s ease-in-out infinite alternate}@keyframes gim{from{transform:rotate(8deg)}to{transform:rotate(-8deg)}}"
        ".fl{animation:fl .5s linear infinite}@keyframes fl{to{stroke-dashoffset:-8}}"
        f".st{{animation:st 3s steps(1) infinite}}.st1{{animation-delay:1s}}.st2{{animation-delay:2s}}"
        f"@keyframes st{{0%{{fill:{C['blue']}}}33.3%,100%{{fill:{C['muted']}}}}}")


def art_loop(s, p, x, y, w, h):
    """Fallback for any project: three named stages and a dot going round the loop."""
    names = p.get("art_steps", ["Idea", "Build", "Ship"])[:3]
    bw, gap = 104, 46
    bx0 = x + (w - (3 * bw + 2 * gap)) / 2
    by = y + 56
    for i, name in enumerate(names):
        bx = bx0 + i * (bw + gap)
        s.text(bx, by - 10, f"0{i+1}", "mono", 10.5, 500, fill=C["muted"], ls=1.2)
        s.add(f'<rect x="{bx:.1f}" y="{by}" width="{bw}" height="40" rx="4" {BOX}/>')
        s.text(bx + bw / 2, by + 25, name, "mono", 12.5, 500, fill=C["ink"], anchor="middle", upper=True)
        if i < 2:
            arrow(s, bx + bw + 6, by + 20, bx + bw + gap - 6)
    x1, x3 = bx0 + bw / 2, bx0 + 2 * (bw + gap) + bw / 2
    ret = f"M{x3:.1f} {by+40} C{x3:.1f} {by+110} {x1:.1f} {by+110} {x1:.1f} {by+40}"
    s.add(f'<path d="{ret}" stroke="{C["blue"]}" stroke-width="1.4" fill="none" stroke-dasharray="4 4"/>')
    s.text(x + w / 2, by + 100, "repeat", "mono", 10.5, fill=C["muted"], ls=1.2, anchor="middle", upper=True)
    s.add(f'<circle class="a dot" r="4" fill="{C["blue"]}"/>')
    s.css.append(ANIM_BASE + f".dot{{offset-path:path('{ret}');animation:go 5s cubic-bezier(.45,0,.55,1) infinite}}"
                 "@keyframes go{from{offset-distance:0%}to{offset-distance:100%}}")


def art_telemetry(s, p, x, y, w, h):
    """A live plot: roll, pitch and yaw traces scroll past like a serial monitor."""
    import math
    px0, px1, py0, py1 = x + 20, x + w - 20, y + 40, y + h - 34
    L, mid, amp = px1 - px0, (py0 + py1) / 2, (py1 - py0) / 2 - 8
    s.defs.append(f'<clipPath id="plot"><rect x="{px0}" y="{py0}" width="{L}" height="{py1-py0}"/></clipPath>')
    s.add(f'<line x1="{px0}" x2="{px1}" y1="{mid}" y2="{mid}" stroke="{C["blue_soft"]}" stroke-width="1" stroke-dasharray="2 4"/>')
    traces = [("Roll", "blue", (1, 0.0, 0.55), (3, 1.0, 0.25)),
              ("Pitch", "sea", (2, 2.0, 0.45), (5, 0.3, 0.15)),
              ("Yaw", "roof", (1, 4.0, 0.25), (4, 2.5, 0.1))]
    s.add('<g clip-path="url(#plot)"><g class="a scroll">')
    for _, col, *waves in traces:
        pts = []
        for i in range(0, 2 * int(L) + 1, 4):
            t = 2 * math.pi * i / L
            v = sum(a * math.sin(k * t + ph) for k, ph, a in waves)
            pts.append(f"{px0 + i:.0f},{mid - v * amp:.1f}")
        s.add(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{C[col]}" stroke-width="1.4" stroke-linejoin="round"/>')
    s.add("</g></g>")
    s.add(f'<rect x="{px0}" y="{py0}" width="{L}" height="{py1-py0}" fill="none" stroke="{C["rule"]}"/>')
    lx = px0
    for name, col, *_ in traces:
        s.add(f'<rect x="{lx}" y="{y+21}" width="8" height="8" fill="{C[col]}"/>')
        s.text(lx + 14, y + 29, name, "mono", 10.5, 500, fill=C["muted"], ls=1.2, upper=True)
        lx += 14 + fnt("mono", 500).width(name.upper(), 10.5, 1.2) + 20
    s.add(f'<circle class="a live" cx="{px1-6}" cy="{y+25}" r="3.5" fill="{C["red"] if "red" in C else "#c4302b"}"/>')
    s.text(px1 - 16, y + 29, "Live", "mono", 10.5, 500, fill=C["muted"], ls=1.2, anchor="end", upper=True)
    s.text(px0, y + h - 14, p.get("art_text", "STM32 → Web Serial"), "mono", 10.5, fill=C["muted"], ls=1.2, upper=True)
    s.text(px1, y + h - 14, "deg / time", "mono", 10.5, fill=C["faint"], ls=1.2, anchor="end", upper=True)
    s.css.append(ANIM_BASE + f".scroll{{animation:scroll 10s linear infinite}}"
                 f"@keyframes scroll{{to{{transform:translateX(-{L:.0f}px)}}}}"
                 ".live{animation:pulse 1.6s ease-in-out infinite}@keyframes pulse{50%{opacity:.25}}")


ARTS = {"shell": art_shell, "rocket": art_rocket, "loop": art_loop, "telemetry": art_telemetry}


def project_art(s, p, x, y, w, h):
    if p.get("media"):
        name = p["media"]
        ext = name.rsplit(".", 1)[-1].lower()
        mime = {"gif": "image/gif", "webp": "image/webp", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}[ext]
        with open(os.path.join(HERE, "images", name), "rb") as fh:
            uri = f"data:{mime};base64," + base64.b64encode(fh.read()).decode()
        s.plate(uri, x, y, w, h, cid="media")
        return
    s.grid_pattern()
    s.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="{C["card"]}"/>')
    s.add(f'<rect x="{x+.5}" y="{y+.5}" width="{w-1}" height="{h-1}" rx="5" fill="url(#grid)" stroke="{C["rule2"]}"/>')
    ARTS.get(p.get("art", "loop"), art_loop)(s, p, x, y, w, h)


def project_layout(p):
    lines = wrap(p["blurb"], "serif", 17, 460)
    return lines, 300 + len(lines) * 26 + 20 + 24 + 22 + 50


def project(cfg, p, idx, H):
    W = 500
    lines, _ = project_layout(p)
    s = Svg(W, H, f'{p["name"]}: {p["blurb"]}')
    s.card()
    project_art(s, p, 16, 16, W - 32, 196)
    s.text(20, 244, f"FIG_{idx:03d}  ·  {p['status']}", "mono", 11, 500, fill=C["blue"], ls=1.5, upper=True)
    s.text(20, 280, p["name"], "serif", 30, 500, fill=C["ink"], ls=-0.4)
    y = 310
    for line in lines:
        s.text(20, y, line, "serif", 17, fill=C["ink2"])
        y += 26
    x, y = 20, y + 14
    for tag, col in p["tags"]:
        tw = fnt("mono", 500).width(tag.upper(), 10.5, 1)
        cw = tw + 24
        s.add(f'<rect x="{x}" y="{y}" width="{cw:.1f}" height="24" rx="12" fill="{C["card"]}" stroke="{C[col]}"/>')
        s.text(x + 12, y + 16, tag, "mono", 10.5, 500, fill=C[col], ls=1, upper=True)
        x += cw + 8
    s.add(f'<line x1="16" x2="{W-16}" y1="{H-44}" y2="{H-44}" stroke="{C["rule"]}"/>')
    path = f'{cfg["username"]}/{p["repo"]}'
    while fnt("mono").width(path, 11, 0.4) > W - 170:
        path = path[:-2] + "…"
        path = path.replace("……", "…")
    s.text(20, H - 18, path, "mono", 11, fill=C["muted"], ls=0.4)
    s.text(W - 20, H - 18, "Open repo →", "mono", 11, 500, fill=C["blue"], anchor="end", ls=1.2, upper=True)
    s.save(f"project-{idx}.svg")


def stack(cfg):
    W, x0, x1 = 1000, 200, 964
    rows, y = [], 70
    for g in cfg["stack"]:
        chips, x, ry = [], x0, y
        for it in g["items"]:
            cw = fnt("mono").width(it, 13) + 40
            if x + cw > x1:
                x, ry = x0, ry + 44
            chips.append((x, ry, cw, it))
            x += cw + 10
        rows.append((g, y, chips))
        y = ry + 56
    H = int(y + 30)
    s = Svg(W, H, "Toolbox. " + ". ".join(f'{g["label"]}: {", ".join(g["items"])}' for g in cfg["stack"]))
    s.grid_pattern()
    s.card()
    s.add(f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="8" fill="url(#grid)"/>')
    s.text(36, 40, "FIG_003  ·  Toolbox", "mono", 11, 500, fill=C["faint"], ls=1.5, upper=True)
    for g, gy, chips in rows:
        col = C[g["color"]]
        s.text(36, gy + 20, g["label"], "mono", 11, 500, fill=C["muted"], ls=1.4, upper=True)
        for cx, cy, cw, it in chips:
            dash = ' stroke-dasharray="4 3"' if g.get("learning") else ""
            fill = C["paper"] if g.get("learning") else C["card"]
            s.add(f'<rect x="{cx}" y="{cy}" width="{cw:.1f}" height="30" rx="15" fill="{fill}" stroke="{col}"{dash}/>')
            s.add(f'<rect x="{cx+14}" y="{cy+12}" width="6" height="6" fill="{col}"/>')
            s.text(cx + 28, cy + 20, it, "mono", 13, fill=C["ink"])
    if cfg.get("stack_note"):
        s.text(W - 36, H - 22, cfg["stack_note"], "serif", 15, style="italic", fill=C["ink2"], anchor="end")
    s.save("stack.svg")


# ---------------------------------------------------------------- numbers

QUERY = """query($login:String!){user(login:$login){
 followers{totalCount}
 repositories(ownerAffiliations:OWNER,isFork:false,privacy:PUBLIC,first:100){totalCount
  nodes{stargazerCount languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name}}}}}
 contributionsCollection{contributionCalendar{totalContributions weeks{contributionDays{contributionCount date}}}}}}"""


def fetch_numbers(login, hide):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "profile-readme-builder"})
    with urllib.request.urlopen(req, timeout=30) as r:
        u = json.load(r)["data"]["user"]
    langs = {}
    for n in u["repositories"]["nodes"]:
        for e in n["languages"]["edges"]:
            if e["node"]["name"] not in hide:
                langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    cal = u["contributionsCollection"]["contributionCalendar"]
    weeks = [(w["contributionDays"][0]["date"], sum(d["contributionCount"] for d in w["contributionDays"]))
             for w in cal["weeks"]][-52:]
    return {
        "contributions": cal["totalContributions"],
        "repos": u["repositories"]["totalCount"],
        "stars": sum(n["stargazerCount"] for n in u["repositories"]["nodes"]),
        "followers": u["followers"]["totalCount"],
        "weeks": weeks, "langs": langs,
    }


def demo_numbers():
    rnd = random.Random(7)
    start = datetime.date.today() - datetime.timedelta(weeks=52)
    weeks = [((start + datetime.timedelta(weeks=i)).isoformat(),
              max(0, int(rnd.gauss(14, 9) + 10 * (i > 30)))) for i in range(52)]
    return {"contributions": sum(c for _, c in weeks), "repos": 23, "stars": 148, "followers": 61,
            "weeks": weeks, "langs": {"C": 410000, "Python": 220000, "TypeScript": 120000, "Shell": 40000, "C++": 30000, "Lua": 9000}}


def numbers(cfg, data):
    W, H = 1000, 470
    s = Svg(W, H, "Numbers from GitHub" + (f': {data["contributions"]} contributions in the last year, '
                                           f'{data["repos"]} public repositories, {data["stars"]} stars, '
                                           f'{data["followers"]} followers.' if data else ": not generated yet."))
    s.grid_pattern()
    s.card()
    s.text(36, 40, "FIG_004  ·  Numbers", "mono", 11, 500, fill=C["faint"], ls=1.5, upper=True)
    stats = [("Contributions · 12 mo", "contributions", "blue"), ("Public repos", "repos", "sea"),
             ("Stars earned", "stars", "roof"), ("Followers", "followers", "grass")]
    for i, (lab, key, col) in enumerate(stats):
        x = 36 + i * 232
        s.add(f'<rect x="{x}" y="62" width="22" height="3" fill="{C[col]}"/>')
        val = f"{data[key]:,}" if data else "—"
        s.text(x, 112, val, "serif", 44, 500, fill=C["ink"], ls=-0.8)
        s.text(x, 138, lab, "mono", 10.5, 500, fill=C["muted"], ls=1.2, upper=True)

    # weekly bars
    cx0, cx1, cy0, cy1 = 36, 964, 186, 296
    s.text(cx0, 174, "Last 52 weeks", "mono", 10.5, 500, fill=C["muted"], ls=1.2, upper=True)
    s.add(f'<rect x="{cx0}" y="{cy0}" width="{cx1-cx0}" height="{cy1-cy0}" fill="url(#grid)" stroke="{C["rule2"]}"/>')
    if data and data["weeks"]:
        weeks = data["weeks"]
        peak = max(c for _, c in weeks) or 1
        step = (cx1 - cx0) / len(weeks)
        pi = max(range(len(weeks)), key=lambda i: weeks[i][1])
        last_month = None
        for i, (d, c) in enumerate(weeks):
            bx = cx0 + i * step + step * 0.2
            bh = max(1.5, (cy1 - cy0 - 14) * c / peak) if c else 1.5
            col = C["blue"] if c else C["faint"]
            if i == pi:
                col = C["sea"]
            s.add(f'<rect x="{bx:.1f}" y="{cy1-bh:.1f}" width="{step*0.6:.1f}" height="{bh:.1f}" fill="{col}"/>')
            m = d[:7]
            if m != last_month:
                if last_month is not None:
                    s.text(bx, cy1 + 18, datetime.date.fromisoformat(d).strftime("%b"), "mono", 10, fill=C["muted"], ls=0.8, upper=True)
                last_month = m
        s.text(cx1, 174, f"Busiest week · {weeks[pi][1]} contributions", "mono", 10.5, 500,
               fill=C["sea"], ls=1.2, anchor="end", upper=True)
    else:
        s.text((cx0 + cx1) / 2, (cy0 + cy1) / 2 + 6, "Fills in after the first workflow run.",
               "serif", 17, style="italic", fill=C["muted"], anchor="middle")

    # languages
    ly = 352
    s.text(36, ly, "Languages · by bytes in public repos", "mono", 10.5, 500, fill=C["muted"], ls=1.2, upper=True)
    bx0, bw = 36, 928
    if data and data["langs"]:
        items = sorted(data["langs"].items(), key=lambda kv: -kv[1])
        top, rest = items[:5], sum(v for _, v in items[5:])
        if rest:
            top.append(("Other", rest))
        total = sum(v for _, v in top)
        x, lx = bx0, 36
        for i, (name, v) in enumerate(top):
            col = C["faint"] if name == "Other" else C[LANG_COLORS[i % len(LANG_COLORS)]]
            w = bw * v / total
            s.add(f'<rect x="{x:.1f}" y="{ly+14}" width="{max(w-3, 1):.1f}" height="12" rx="2" fill="{col}"/>')
            x += w
            pct = f"{100 * v / total:.0f}%" if v / total >= 0.01 else "<1%"
            s.add(f'<rect x="{lx}" y="{ly+46}" width="8" height="8" fill="{col}"/>')
            s.text(lx + 14, ly + 54, name, "mono", 11.5, fill=C["ink2"])
            nw = fnt("mono").width(name, 11.5)
            s.text(lx + 20 + nw, ly + 54, pct, "mono", 11.5, fill=C["muted"])
            lx += 20 + nw + fnt("mono").width(pct, 11.5) + 28
    else:
        s.add(f'<rect x="{bx0}" y="{ly+14}" width="{bw}" height="12" rx="2" fill="{C["rule2"]}"/>')
    s.add(f'<line x1="36" x2="964" y1="{H-46}" y2="{H-46}" stroke="{C["rule"]}"/>')
    stamp = datetime.date.today().isoformat() if data else "not yet"
    s.text(36, H - 22, f"Updated {stamp}  ·  by GitHub Actions", "mono", 10.5, fill=C["faint"], ls=1, upper=True)
    s.text(964, H - 22, "Live from the GitHub API", "mono", 10.5, fill=C["faint"], ls=1, anchor="end", upper=True)
    s.save("numbers.svg")


# ---------------------------------------------------------------- links + footer

def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def link_button(l):
    tw = fnt("mono", 500).width(l["label"].upper(), 12, 1.4)
    W, H = int(tw + 64), 44
    s = Svg(W, H, l["label"])
    s.add(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="6" fill="{C["paper"]}" stroke="{C["rule"]}"/>')
    s.add(f'<rect x="20" y="18" width="8" height="8" fill="{C[l["color"]]}"/>')
    s.text(38, 26.5, l["label"], "mono", 12, 500, fill=C["ink"], ls=1.4, upper=True)
    s.save(f"link-{slug(l['label'])}.svg")


def footer(cfg):
    f = cfg["footer"]
    W, H = 1000, 270
    s = Svg(W, H, f'{f["title"].replace("*", "")} {f["text"]}')
    s.card()
    s.plate(image_uri(f["image"], 900), 16, 16, 460, H - 32, cid="tram")
    x0, x1 = 516, 956
    s.text(x0, 62, "FIG_END  ·  Last stop", "mono", 11, 500, fill=C["blue"], ls=1.5, upper=True)
    s.rich(x0, 108, f["title"], 34, 500)
    y = 144
    for line in wrap(f["text"], "serif", 17, x1 - x0):
        s.text(x0, y, line, "serif", 17, fill=C["ink2"])
        y += 26
    ty = 214
    s.add(f'<line x1="{x0}" x2="{x1}" y1="{ty}" y2="{ty}" stroke="{C["blue"]}" stroke-width="1.4"/>')
    stops = f.get("stops", [])
    for i, name in enumerate(stops):
        sx = x0 + (x1 - x0) * i / max(1, len(stops) - 1)
        s.add(f'<circle cx="{sx:.1f}" cy="{ty}" r="4.5" fill="{C["card"]}" stroke="{C["blue"]}" stroke-width="1.4"/>')
        anchor = "start" if i == 0 else "end" if i == len(stops) - 1 else "middle"
        s.text(sx, ty + 24, name, "mono", 10.5, 500, fill=C["muted"], ls=1.2, anchor=anchor, upper=True)
    # the one ambient animation on the page: a tram riding between the stops
    s.css.append(f"@keyframes ride{{from{{transform:translateX(0)}}to{{transform:translateX({x1-x0}px)}}}}"
                 ".tram{animation:ride 9s cubic-bezier(.45,0,.55,1) infinite alternate}"
                 "@media (prefers-reduced-motion:reduce){.tram{animation:none;transform:translateX(220px)}}")
    s.add(f'<g class="tram"><rect x="{x0-9}" y="{ty-5}" width="18" height="10" rx="3" fill="{C["blue"]}"/></g>')
    s.save("footer.svg")


# ---------------------------------------------------------------- readme

def readme(cfg, P):
    u, n = cfg["username"], cfg["name"]
    proj = "\n".join(
        f'<a href="https://github.com/{u}/{p["repo"]}"><img src="assets/project-{i}.svg" width="49%" '
        f'alt="{escape(p["name"])}: {escape(p["blurb"])}"></a>' for i, p in enumerate(P, 1))
    links = "\n".join(
        f'<a href="{escape(l["url"])}"><img src="assets/link-{slug(l["label"])}.svg" height="44" alt="{escape(l["label"])}"></a>'
        for l in cfg["links"])
    about_alt = " ".join(f'IN: {p["q"]} OUT: {p["a"]}' for p in cfg["about"])
    return f"""<!-- Generated by build/build.py from build/profile.json. Edit those, not this file. -->

<p align="center">
<img src="assets/hero.svg" width="100%" alt="{escape(n)}: {escape(cfg['hero']['title'].replace('*', ''))} {escape(cfg['hero']['lede'])}">
</p>

<img src="assets/divider-01.svg" width="100%" alt="01 · About">

<img src="assets/about.svg" width="100%" alt="{escape(about_alt)}">

<img src="assets/divider-02.svg" width="100%" alt="02 · Now building">

<p align="center">
{proj}
</p>

<img src="assets/divider-03.svg" width="100%" alt="03 · Toolbox">

<img src="assets/stack.svg" width="100%" alt="Toolbox: {escape('; '.join(g['label'] + ': ' + ', '.join(g['items']) for g in cfg['stack']))}">

<img src="assets/divider-04.svg" width="100%" alt="04 · Numbers">

<img src="assets/numbers.svg" width="100%" alt="Contributions, repositories, stars, followers and top languages, updated daily">

<img src="assets/divider-05.svg" width="100%" alt="05 · Say hello">

<p align="center">
{links}
</p>

<img src="assets/footer.svg" width="100%" alt="{escape(cfg['footer']['title'].replace('*', ''))}">
"""


def preview(md):
    """A local page that mimics GitHub's README column, with a light/dark switch. Not needed on GitHub."""
    html = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Profile preview</title><style>
body{{margin:0;font:14px -apple-system,Segoe UI,sans-serif;background:#fff;color:#1f2328}}
body.dark{{background:#0d1117;color:#e6edf3}}
.bar{{position:sticky;top:0;padding:10px 16px;background:inherit;border-bottom:1px solid #d1d9e0;display:flex;gap:8px;align-items:center}}
.bar button{{font:12px ui-monospace,Consolas,monospace;padding:4px 10px;border:1px solid #d1d9e0;background:#f6f8fa;border-radius:6px;cursor:pointer}}
.box{{max-width:880px;margin:24px auto;border:1px solid #d1d9e0;border-radius:6px;padding:24px 32px}}
body.dark .box,body.dark .bar{{border-color:#3d444d}}
.box p{{margin:0 0 16px}} .box img{{max-width:100%;vertical-align:middle}} .box>img{{display:block;margin:0 0 16px}}
@media (max-width:600px){{.box{{padding:16px;margin:12px}}}}
</style></head><body><div class="bar"><span>preview / README.md</span>
<button onclick="document.body.classList.toggle('dark')">toggle GitHub dark mode</button></div>
<div class="box">{html}</div></body></html>"""


def main():
    with open(os.path.join(HERE, "profile.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    hide = set(cfg.get("numbers", {}).get("hide_languages", []))
    login = os.environ.get("PROFILE_LOGIN") or cfg["username"]
    if "--demo" in sys.argv:
        data = demo_numbers()
    else:
        data = fetch_numbers(login, hide)
    if "--numbers" in sys.argv:
        if data is None:
            sys.exit("GITHUB_TOKEN is not set, so there is nothing to fetch.")
        numbers(cfg, data)
        return
    print("Building assets:")
    hero(cfg)
    for num, title in [("01", "About"), ("02", "Now building"), ("03", "Toolbox"), ("04", "Numbers"), ("05", "Say hello")]:
        divider(num, title)
    about(cfg)
    P = cfg["projects"]
    H = max(project_layout(p)[1] for p in P)
    for i, p in enumerate(P, 1):
        project(cfg, p, i, H)
    stack(cfg)
    numbers(cfg, data)
    for l in cfg["links"]:
        link_button(l)
    footer(cfg)
    md = readme(cfg, P)
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    with open(os.path.join(HERE, "preview.html"), "w", encoding="utf-8") as fh:
        fh.write(preview(md).replace('src="assets/', 'src="../assets/'))
    print("  README.md and build/preview.html written")


if __name__ == "__main__":
    main()

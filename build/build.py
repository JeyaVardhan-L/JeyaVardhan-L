#!/usr/bin/env python3
"""Builds the profile README and its SVG cards from profile.json.

    python build/build.py

GitHub strips CSS, scripts and web fonts from READMEs, but it shows SVG images, and an SVG
can carry its own fonts, styles and animations. So every block here is an SVG with
Source Serif 4 and JetBrains Mono embedded (subset), animated with CSS and SMIL.
"""
import base64, io, json, os, re
from xml.sax.saxutils import escape
from fontTools.ttLib import TTFont
from fontTools import subset
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")

# Dark field-guide palette: night paper, light ink, the same blue lifted for dark backgrounds,
# and accent colours taken from the paintings (sea, roof tiles, grass, sun).
C = {
    "panel": "#0f1218", "card": "#151a22", "edge": "#262c37",
    "ink": "#eceef2", "ink2": "#b3b8c3", "muted": "#7d8492", "faint": "#4f5664",
    "blue": "#7f90ff", "blue2": "#8fa0ff", "grid": "rgba(127,144,255,0.055)",
    "sea": "#5bbccc", "roof": "#e8915f", "grass": "#86c46f", "sun": "#ecc463", "amber": "#e6ab4f",
    "sticker": "#f5f1e8",
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

    def rich(self, x, y, s, size, weight=500, fill=C["ink"], accent=C["blue2"]):
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


# ---------------------------------------------------------------- stickers
# A painting becomes a die-cut sticker: cream border, soft shadow, a slight tilt, and a slow float.
# Inside it, parts of the painting move: water ripples, leaves rustle, clouds drift, and a gloss
# shine sweeps across now and then. Regions are fractions of the image: (x0, y0, x1, y1).

EFFECTS = {
    # kind: (turbulence baseFrequency from, to, displacement scale, seconds)
    "water": ("0.004 0.055", "0.005 0.075", 7, 6),
    "leaves": ("0.025 0.03", "0.032 0.036", 5, 4.5),
}


def sticker(s, sid, spec, cx, cy, w, rot, phase=0.0):
    uri, aspect = image_uri(spec["image"])
    h = w / aspect
    x, y, b = cx - w / 2, cy - h / 2, 8
    s.defs.append(f'<image id="{sid}" href="{uri}" xlink:href="{uri}" x="{x:.1f}" y="{y:.1f}" '
                  f'width="{w:.1f}" height="{h:.1f}" preserveAspectRatio="none"/>')
    s.defs.append(f'<clipPath id="{sid}-clip"><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="7"/></clipPath>')
    if "shadow" not in s.css:
        s.defs.append('<filter id="shadow" x="-20%" y="-20%" width="140%" height="150%">'
                      '<feGaussianBlur stdDeviation="9"/></filter>'
                      '<filter id="feather" x="-20%" y="-20%" width="140%" height="140%">'
                      '<feGaussianBlur stdDeviation="5"/></filter>')
        s.css.add("shadow")
    s.css.add("@keyframes float{0%,100%{transform:translateY(0) rotate(0deg)}50%{transform:translateY(-7px) rotate(.8deg)}}"
              ".float{animation:float 7s ease-in-out infinite}"
              "@keyframes drift{from{transform:translateX(-6px)}to{transform:translateX(9px)}}"
              ".drift{animation:drift 14s ease-in-out infinite alternate}"
              "@keyframes shine{0%,62%{transform:translateX(0)}100%{transform:translateX(var(--d))}}"
              ".shine{animation:shine 7s cubic-bezier(.45,0,.55,1) infinite}")
    s.add(f'<g class="a float" style="transform-origin:{cx}px {cy}px;animation-delay:-{phase}s">'
          f'<g transform="rotate({rot} {cx} {cy})">')
    s.add(f'<rect x="{x-b+4:.1f}" y="{y-b+12:.1f}" width="{w+2*b:.1f}" height="{h+2*b:.1f}" rx="14" '
          f'fill="#000" opacity="0.55" filter="url(#shadow)"/>')
    s.add(f'<rect x="{x-b:.1f}" y="{y-b:.1f}" width="{w+2*b:.1f}" height="{h+2*b:.1f}" rx="14" fill="{C["sticker"]}"/>')
    s.add(f'<g clip-path="url(#{sid}-clip)"><use href="#{sid}" xlink:href="#{sid}"/>')
    for i, (kind, (fx0, fy0, fx1, fy1)) in enumerate(spec.get("motion", [])):
        rx, ry, rw, rh = x + fx0 * w, y + fy0 * h, (fx1 - fx0) * w, (fy1 - fy0) * h
        mid = f"{sid}-m{i}"
        s.defs.append(f'<mask id="{mid}" maskUnits="userSpaceOnUse" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}">'
                      f'<rect x="{rx+6:.1f}" y="{ry+6:.1f}" width="{max(rw-12, 1):.1f}" height="{max(rh-12, 1):.1f}" '
                      f'fill="#fff" filter="url(#feather)"/></mask>')
        if kind == "drift":
            s.add(f'<g mask="url(#{mid})"><g class="a drift" style="animation-delay:-{phase*2:.1f}s">'
                  f'<use href="#{sid}" xlink:href="#{sid}"/></g></g>')
            continue
        f0, f1, scale, dur = EFFECTS[kind]
        fid = f"{sid}-f{i}"
        s.defs.append(
            f'<filter id="{fid}" filterUnits="userSpaceOnUse" x="{rx-10:.1f}" y="{ry-10:.1f}" width="{rw+20:.1f}" height="{rh+20:.1f}">'
            f'<feTurbulence type="turbulence" baseFrequency="{f0}" numOctaves="2" seed="{3+i}" result="n">'
            f'<animate attributeName="baseFrequency" dur="{dur}s" values="{f0};{f1};{f0}" repeatCount="indefinite"/>'
            f'</feTurbulence><feDisplacementMap in="SourceGraphic" in2="n" scale="{scale}" '
            f'xChannelSelector="R" yChannelSelector="G"/></filter>')
        s.add(f'<g mask="url(#{mid})"><use href="#{sid}" xlink:href="#{sid}" filter="url(#{fid})"/></g>')
    # gloss: a soft diagonal band crossing the sticker every few seconds
    s.add(f'<polygon class="a shine" style="--d:{w*1.9:.0f}px;animation-delay:-{phase:.1f}s" '
          f'points="{x-w*0.45:.1f},{y+h:.1f} {x-w*0.25:.1f},{y:.1f} {x-w*0.1:.1f},{y:.1f} {x-w*0.3:.1f},{y+h:.1f}" '
          f'fill="#fff" opacity="0.16"/>')
    s.add("</g></g></g>")


# ---------------------------------------------------------------- blocks

def hero(cfg):
    h = cfg["hero"]
    W, H = 1000, 470
    s = Svg(W, H, f'{cfg["name"]}. {" ".join(h["title_lines"]).replace("*", "")} {h["lede"]}')
    s.panel()
    x = 56
    s.text(x, 96, h["eyebrow"], "mono", 12, 500, fill=C["muted"], ls=2.2, upper=True)
    y = 160
    for line in h["title_lines"]:
        s.rich(x, y, line, 50, 500)
        y += 58
    y += 10
    for line in wrap(h["lede"], "serif", 19, 430):
        s.text(x, y, line, "serif", 19, fill=C["ink2"])
        y += 29
    typer(s, x, y + 44, h["prompt"], h["typing"])
    st = h["stickers"]
    sticker(s, "st1", st[0], 760, 158, 300, -5, phase=0)
    sticker(s, "st2", st[1], 790, 330, 236, 4.5, phase=3.2)
    s.save("hero.svg")


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
        s.add(f'<g class="a v{k}"><text x="{px:.1f}" y="{y}" class="m" font-size="{size}" fill="{C["blue2"]}">{escape(p)}</text>'
              f'<g class="a t{k}"><rect x="{px:.1f}" y="{y-size}" width="{tw+cw*2:.1f}" height="{size+6}" fill="{C["panel"]}"/>'
              f'<rect class="a caret" x="{px+1:.1f}" y="{y-size+2}" width="{cw*0.6:.1f}" height="{size+1}" fill="{C["blue2"]}"/></g></g>')
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
        s.add(f'<rect x="{x:.1f}" y="20" width="4" height="4" fill="#3b4250"/>')
        x += 9
    x = W - 6
    while x >= right_start:
        s.add(f'<rect x="{x:.1f}" y="20" width="4" height="4" fill="#3b4250"/>')
        x -= 9
    s.used.add(("mono", 500, "normal"))
    s.add(f'<text x="500" y="26.5" class="m" font-size="12" font-weight="500" letter-spacing="1.4" '
          f'text-anchor="middle" fill="{C["muted"]}"><tspan fill="{C["blue2"]}">{num}</tspan>'
          f'  ·  {escape(title.upper())}</text>')
    s.save(f"divider-{num}.svg")


def project_row(cfg, p, i):
    W, H = 1000, 76
    s = Svg(W, H, f'{p["name"]}: {p["blurb"]}')
    s.add(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="10" fill="{C["panel"]}" stroke="{C["edge"]}"/>')
    s.add(f'<rect x="0.5" y="14" width="3" height="{H-28}" rx="1.5" fill="{C[p["tags"][0][1]]}"/>')
    s.text(28, 33, f"{i:02d}", "mono", 12, 500, fill=C["faint"], ls=1)
    s.text(68, 34, p["name"], "serif", 22, 500, fill=C["ink"], ls=-0.2)
    # tags on the right, then an arrow
    x = W - 64
    chips = []
    for tag, col in reversed(p["tags"]):
        cw = fnt("mono", 500).width(tag.upper(), 10.5, 1) + 22
        x -= cw
        chips.append((x, cw, tag, col))
        x -= 8
    for cx, cw, tag, col in chips:
        s.add(f'<rect x="{cx:.1f}" y="26" width="{cw:.1f}" height="24" rx="12" fill="none" stroke="{C[col]}" stroke-opacity="0.7"/>')
        s.text(cx + 11, 42, tag, "mono", 10.5, 500, fill=C[col], ls=1, upper=True)
    s.css.add("@keyframes nudge{0%,70%,100%{transform:translateX(0)}80%{transform:translateX(5px)}}"
              ".nudge{animation:nudge 4s ease-in-out infinite}")
    s.used.add(("mono", 500, "normal"))
    s.add(f'<text class="m a nudge" style="animation-delay:-{i*0.6}s" x="{W-30}" y="45" font-size="18" '
          f'font-weight="500" fill="{C["blue2"]}" text-anchor="end">→</text>')
    s.text(68, 58, fit(p["blurb"], "serif", 15, x - 68 - 20), "serif", 15, fill=C["ink2"])
    s.save(f"project-{i}.svg")


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


def footer(cfg):
    f = cfg["footer"]
    W, H = 1000, 300
    s = Svg(W, H, f'{f["title"].replace("*", "")} {f["text"]}')
    s.panel()
    x = 56
    s.text(x, 104, f["eyebrow"], "mono", 11, 500, fill=C["blue2"], ls=1.8, upper=True)
    s.rich(x, 154, f["title"], 38, 500)
    y = 192
    for line in wrap(f["text"], "serif", 17, 400):
        s.text(x, y, line, "serif", 17, fill=C["ink2"])
        y += 27
    st = f["stickers"]
    sticker(s, "st3", st[0], 655, 150, 250, 4, phase=1.5)
    sticker(s, "st4", st[1], 845, 158, 240, -4, phase=4.6)
    s.save("footer.svg")


# ---------------------------------------------------------------- readme

def readme(cfg):
    n, P = cfg["name"], cfg["projects"]
    u = cfg["username"]
    rows = "\n".join(
        f'<a href="https://github.com/{u}/{p["repo"]}"><img src="assets/project-{i}.svg" width="100%" '
        f'alt="{escape(p["name"])}: {escape(p["blurb"])}"></a>' for i, p in enumerate(P, 1))
    links = "\n".join(
        f'<a href="{escape(l["url"])}"><img src="assets/link-{slug(l["label"])}.svg" height="44" alt="{escape(l["label"])}"></a>'
        for l in cfg["links"])
    stack_alt = "; ".join(g["label"] + ": " + ", ".join(g["items"]) for g in cfg["stack"])
    title = " ".join(cfg["hero"]["title_lines"]).replace("*", "")
    return f"""<!-- Generated by build/build.py from build/profile.json. Edit those, not this file. -->

<img src="assets/hero.svg" width="100%" alt="{escape(n)}: {escape(title)} {escape(cfg['hero']['lede'])}">

<img src="assets/divider-01.svg" width="100%" alt="01 · Projects">

<p>
{rows}
</p>

<img src="assets/divider-02.svg" width="100%" alt="02 · Toolbox">

<img src="assets/stack.svg" width="100%" alt="Toolbox: {escape(stack_alt)}">

<img src="assets/divider-03.svg" width="100%" alt="03 · Elsewhere">

<p align="center">
{links}
</p>

<img src="assets/footer.svg" width="100%" alt="{escape(cfg['footer']['title'].replace('*', ''))}">
"""


def preview(md):
    """A local page that mimics GitHub's README column. Not needed on GitHub."""
    html = re.sub(r"<!--.*?-->", "", md, flags=re.S).replace('src="assets/', 'src="../assets/')
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Profile preview</title><style>
body{{margin:0;font:14px -apple-system,Segoe UI,sans-serif;background:#0d1117;color:#e6edf3}}
body.light{{background:#fff;color:#1f2328}}
.bar{{position:sticky;top:0;z-index:1;padding:10px 16px;background:inherit;border-bottom:1px solid #3d444d;display:flex;gap:8px;align-items:center}}
.bar button{{font:12px ui-monospace,Consolas,monospace;padding:4px 10px;border:1px solid #3d444d;background:#151b23;color:inherit;border-radius:6px;cursor:pointer}}
.box{{max-width:880px;margin:24px auto;border:1px solid #3d444d;border-radius:6px;padding:24px 32px}}
.box p{{margin:0 0 16px}} .box img{{max-width:100%;vertical-align:middle}} .box>img{{display:block;margin:0 0 16px}}
@media (max-width:600px){{.box{{padding:16px;margin:12px}}}}
</style></head><body><div class="bar"><span>preview / README.md</span>
<button onclick="document.body.classList.toggle('light')">toggle GitHub light mode</button></div>
<div class="box">{html}</div></body></html>"""


def main():
    with open(os.path.join(HERE, "profile.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    print("Building assets:")
    for name in os.listdir(ASSETS) if os.path.isdir(ASSETS) else []:
        os.remove(os.path.join(ASSETS, name))
    hero(cfg)
    for num, title in [("01", "Projects"), ("02", "Toolbox"), ("03", "Elsewhere")]:
        divider(num, title)
    for i, p in enumerate(cfg["projects"], 1):
        project_row(cfg, p, i)
    stack(cfg)
    for l in cfg["links"]:
        link_button(l)
    footer(cfg)
    md = readme(cfg)
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    with open(os.path.join(HERE, "preview.html"), "w", encoding="utf-8") as fh:
        fh.write(preview(md))
    print("  README.md and build/preview.html written")


if __name__ == "__main__":
    main()

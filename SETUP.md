# Editing the profile

Everything on the page comes from `build/profile.json`. To change something:

```
pip install fonttools pillow
python build/build.py
git add . && git commit -m "Update profile" && git push
```

Never edit `README.md` or `assets/` by hand. The build rewrites them.

## What you can change

- **Hero:** `title_lines` (put `*stars*` around the accent word), `lede`, and `typing`, the phrases typed after `$ now building`.
- **Projects:** each row has a name, repo, a one-line blurb and up to two tags. The first tag's colour also colours the row's left edge.
- **Stickers:** each sticker is a painting from `build/images/` plus a list of moving regions, given as fractions of the image `[x0, y0, x1, y1]`:
  - `water`: ripples
  - `leaves`: rustles
  - `drift`: moves slowly sideways, good for clouds
- **Colours:** the `C` table at the top of `build/build.py`. Tag colours are `blue`, `sea`, `roof`, `grass`, `sun` and `amber`.

To preview locally, run `python -m http.server` in this folder and open `http://localhost:8000/build/preview.html`.

## Why SVG

GitHub removes CSS, scripts and web fonts from READMEs, but it shows SVG images, and an SVG can carry its own fonts and animations. The motion inside the paintings is an animated turbulence filter on the regions you list, so the files stay small. Visitors who have turned on reduced motion in their system settings see everything still.

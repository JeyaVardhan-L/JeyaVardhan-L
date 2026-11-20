# Editing the profile

Everything on the page comes from `build/profile.json`. To change something:

```
pip install fonttools pillow
python build/build.py
git add . && git commit -m "Update profile" && git push
```

Never edit `README.md` or `assets/` by hand. The build rewrites them.

## What you can change

- **Hero:** `name_line` (put `*stars*` around the red accent word), `typing` (the phrases typed after `$ now building`) and `meta`. There is no tagline on purpose; add one to `meta` when you want it.
- **Projects:** two cards side by side, each with a name, repo, blurb and two tags. `more.items` are the chips in the "Also" row, which links to all your repositories.
- **Scenes** (hero, section strips, footer): each one names a painting in `build/images/`, a `crop` of it as fractions `[x0, y0, x1, y1]`, and moving regions in the same units:
  - `water`: ripples, with sun glints
  - `leaves`: sways
  - `drift`: moves slowly sideways, good for clouds

  The painting stays at full resolution. Only its edges break into small pixel blocks and darken into the background.
- **Avatar:** `avatar.png` is your GitHub picture. `crop` (in pixels) picks the part that becomes ASCII art.
- **Commit city:** built from your public contribution calendar. A GitHub Action rebuilds it every day, and whenever `build/` changes. You can also run it from the Actions tab ("Rebuild commit city").
- **Colours:** the `C` table at the top of `build/build.py`. Tag colours are `red`, `coral`, `amber`, `rose` and `sand`.

To preview locally, run `python -m http.server` in this folder and open `http://localhost:8000/build/preview.html`.

## Why SVG

GitHub removes CSS, scripts and web fonts from READMEs, but it shows SVG images, and an SVG can carry its own fonts and animations. The motion in the paintings comes from SVG filters and CSS, so the files stay small. Visitors who have turned on reduced motion in their system settings see everything still.

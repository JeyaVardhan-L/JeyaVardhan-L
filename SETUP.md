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
- **Projects:** each row has a name, repo, a one-line blurb and up to two tags. Keep two or three; `more` is the "read more" line under them.
- **Pixel scenes** (hero, section strips, footer): each one names a painting in `build/images/`, a `crop` of it as fractions `[x0, y0, x1, y1]`, and moving regions in the same units:
  - `water`: rows shimmer, with sparkles
  - `leaves`: sways
  - `drift`: moves slowly sideways, good for clouds

  The build shrinks the painting to pixel art, animates it frame by frame and dithers its edges into the background.
- **Avatar:** `avatar.png` is your GitHub picture. `crop` (in pixels) picks the part that becomes ASCII art.
- **Commit city:** built from your public contribution calendar. A GitHub Action rebuilds it every day, and whenever `build/` changes. You can also run it from the Actions tab ("Rebuild commit city").
- **Colours:** the `C` table at the top of `build/build.py`. Tag colours are `blue`, `sea`, `roof`, `grass`, `sun` and `amber`.

To preview locally, run `python -m http.server` in this folder and open `http://localhost:8000/build/preview.html`.

## Why SVG

GitHub removes CSS, scripts and web fonts from READMEs, but it shows SVG images, and an SVG can carry its own fonts and animations. The pixel scenes are small sprite sheets that CSS steps through, so the files stay small. Visitors who have turned on reduced motion in their system settings see everything still.

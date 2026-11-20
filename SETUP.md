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
- **Scenes:** the hero, the two section strips and the footer are pixel art drawn in code in `build/build.py`: `launch` (TVC rocket), `lidar` (rover and point-cloud scan), `skyline` (night city and a drone) and `batcave` (moon, bats, server racks). Pick them with `hero.scene`, `strips` and `footer.scene`. Each one is plain SVG squares, so it stays sharp at any size, and the moving parts step one pixel at a time.
- **Avatar:** `avatar.png` is your GitHub picture. `crop` (in pixels) picks the part that becomes ASCII art.
- **Commit city:** built from your public contribution calendar. A GitHub Action rebuilds it every day, and whenever `build/` changes. You can also run it from the Actions tab ("Rebuild commit city").
- **Colours:** the `C` table at the top of `build/build.py`. Tag colours are `red`, `crimson`, `rose`, `white` and `steel`.

To preview locally, run `python -m http.server` in this folder and open `http://localhost:8000/build/preview.html`.

## Why SVG

GitHub removes CSS, scripts and web fonts from READMEs, but it shows SVG images, and an SVG can carry its own fonts and animations. The motion is plain CSS, so the files stay small. Visitors who have turned on reduced motion in their system settings see everything still.

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
- **Scenes:** the hero and the two section strips are pixel art drawn in code in `build/build.py`: `launch` (TVC rocket) in the hero, `pcb` (a circuit board with signals running between an STM32, an IMU and a radio) over Projects, and `skyline` (night city and a drone) over the commit city. `lidar` and `batcave` are also there if you want to swap one in. Pick them with `hero.scene` and `strips`. Each one is plain SVG squares, so it stays sharp at any size.
- **Avatar:** `avatar.png` is your GitHub picture. `crop` (in pixels) picks the part that becomes ASCII art.
- **Commit city:** built from your public contribution calendar. A GitHub Action rebuilds it every day, and whenever `build/` changes. You can also run it from the Actions tab ("Rebuild commit city").
- **Toolbox:** a small panel at the very end. Edit `stack` (four groups, each a label and a list). Keep it to things you can talk about.
- **Colours:** the `C` table at the top of `build/build.py`. Tag colours are `blue`, `green`, `purple`, `orange` and `gray`, taken from GitHub's own palette.

To preview locally, run `python -m http.server` in this folder and open `http://localhost:8000/build/preview.html`.

## Why SVG

GitHub removes CSS, scripts and web fonts from READMEs, but it shows SVG images, and an SVG can carry its own fonts and animations. The motion is plain CSS, so the files stay small. Visitors who have turned on reduced motion in their system settings see everything still.

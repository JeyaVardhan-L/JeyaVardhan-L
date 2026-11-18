# Setting up the profile

GitHub shows a README on your profile when it lives in a public repo named exactly like your username.

1. **Make the repo.** On GitHub, create a new public repository called `your-username` (your real username). Leave it empty.
2. **Fill in your details.** Edit `build/profile.json`: name, username, hero text, the IN/OUT answers, projects, toolbox, links. Mark italic accent words with `*stars*`.
3. **Build.** From this folder:
   ```
   pip install fonttools pillow
   python build/build.py
   ```
   This rewrites `README.md` and everything in `assets/`. Open `build/preview.html` through a local server (`python -m http.server`) to check it, with a dark-mode toggle.
4. **Push.**
   ```
   git init -b main
   git add .
   git commit -m "Profile"
   git remote add origin https://github.com/your-username/your-username.git
   git push -u origin main
   ```
5. **Turn on the numbers card.** In the repo: Settings → Actions → General → Workflow permissions → "Read and write permissions". Then Actions → "Update numbers card" → Run workflow. After that it refreshes daily on its own.

## Changing things later

- Text, projects, links: edit `profile.json`, run `build.py`, push.
- Hero and footer paintings: drop a picture in `build/images/` and point to it from `profile.json`.
- Project figures: each project has an animated line-art figure. Set `"art"` to `"shell"` (a pipeline with moving packets), `"rocket"` (a motor that gimbals) or `"loop"` (three stages and a dot going round; set the names with `"art_steps": ["Idea", "Build", "Ship"]`). To use your own animated image instead, put a small GIF or WebP in `build/images/` and set `"media": "demo.gif"`. Keep it under about 1 MB.
- Colours: the `C` table at the top of `build/build.py`. Tag colours are `blue`, `sea`, `roof`, `grass`, `sun`, `amber`.
- Never edit `README.md` or `assets/` by hand. They are regenerated.

## Why it's built this way

GitHub removes CSS, scripts and web fonts from READMEs. Images are allowed, and an SVG image can carry its own fonts and styles inside it. So each block is an SVG with Source Serif 4 and JetBrains Mono embedded (subset to keep files small), which means every visitor sees the same type.

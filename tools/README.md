# tools/

Not used by the GitHub Action — only for regenerating the ASCII-art side of
the card if you swap in a new photo later.

- `source_photo.png` — background-removed source image the ASCII art was traced from.
- `ascii_final.json` — the traced 46×24 character grid `build_svg.py` reads.
- `build_svg.py` — regenerates `dark_mode.svg` / `light_mode.svg` from `ascii_final.json`
  plus the hardcoded personal fields (`ABOUT`, `LANGUAGES`, `HOBBIES`, `CONTACT` near the
  top of the file). Edit those, then run `python tools/build_svg.py` from anywhere —
  it always reads from and writes next to this folder's real location, done.

`update.py` (in the repo root) only ever touches the GitHub-Stats numbers and the
Uptime line — it never re-runs this script, so editing your bio fields here is safe
and won't get overwritten by the daily Action.

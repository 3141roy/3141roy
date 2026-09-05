"""
Generator for dark_mode.svg / light_mode.svg.

Alignment rule (reverse-engineered from a real hand-tuned neofetch card,
Andrew6rant/Andrew6rant's dark_mode.svg): every row right-justifies to the
SAME total character width from the panel's left edge — not a shared
start column. Dots are however many characters make
len(bullet + key + ":" + dots + value) == TOTAL_WIDTH. Short label + short
value -> long dot run. Long label + long value -> short dot run. That's
why rows with wildly different label lengths still end flush on the right.
"""
import json
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent

with open(TOOLS_DIR / "ascii_final.json") as f:
    art = json.load(f)
COLS, ROWS, LINES = art["cols"], art["rows"], art["lines"]

FONT_SIZE = 14
LINE_H = 19
ASCII_X = 24
ASCII_Y0 = 38
STAT_X = 470
WIDTH = 1010
BULLET = ". "
TOTAL_WIDTH = 58  # chars, tuned to this card's ~61-char-wide stat column

# ---- personal fields ----
ABOUT = [
    ("OS", "macOS, Ubuntu"),
    ("Uptime", "24 years, 2 months, 3 days", "uptime_data", "uptime_data_dots"),  # age since birth (2002-06-05), recomputed daily
    ("Host", "Cvent"),
    ("Role", "SRE - II"),
    ("IDE", "VS Code (yes i know)"),
]
LANGUAGES = [
    ("Languages.Programming", "Python, TypeScript, C++"),
    ("Languages.Computer", "YAML, JSON, LaTeX"),
    ("Languages.Real", "English, Hindi, Bengali"),
]
HOBBIES = [
    ("Hobbies", "Football, Video Games"),
]
CONTACT = [
    ("Email", "01rajnikantroy@gmail.com"),
    ("LinkedIn", "rajnnikantroy"),
    ("Instagram", "rajnnikantroy"),
]


def dot_run(just_len):
    """Same special-casing as the reference card: very short gaps skip the
    dots entirely rather than rendering a single lonely '.'."""
    if just_len <= 0:
        return ""
    if just_len == 1:
        return " "
    if just_len == 2:
        return ". "
    return " " + ("." * (just_len - 2)) + " "


def row(y, label, segments, total_width=TOTAL_WIDTH, dots_id=None):
    """
    One right-justified stat line. `segments` is a list of (text, css_class,
    element_id_or_None) rendered after the dot-run — as many as the row
    needs. Dots are sized against the FULL rendered length of every
    segment, so nothing after the first value can silently push the row
    past total_width (that's what broke the Lines-of-Code row).
    """
    prefix = f"{BULLET}{label}:"
    rest_len = sum(len(text) for text, _cls, _id in segments)
    dots = dot_run(max(0, total_width - len(prefix) - rest_len))
    dots_attr = f' id="{dots_id}"' if dots_id else ""
    seg_xml = "".join(
        f'<tspan class="{cls}"{f" id=\"{id_}\"" if id_ else ""}>{text}</tspan>'
        for text, cls, id_ in segments
    )
    return (f'<tspan x="{STAT_X}" y="{y}"><tspan class="dots">{prefix[:2]}</tspan>'
            f'<tspan class="k">{prefix[2:]}</tspan>'
            f'<tspan class="dots"{dots_attr}>{dots}</tspan>{seg_xml}</tspan>')


def block_rows(y, gap, entries):
    out = []
    for entry in entries:
        label, value, val_id, dots_id = (*entry, None, None)[:4]
        out.append(row(y, label, [(value, "v", val_id)], dots_id=dots_id))
        y += gap
    return out, y


def spacer(y):
    return f'<tspan x="{STAT_X}" y="{y}" class="dots">.</tspan>'


def header_rule(y, label):
    dash_len = TOTAL_WIDTH - len(label) - 3
    dashes = "-" * max(dash_len, 3)
    return f'<tspan x="{STAT_X}" y="{y}" class="dots">- <tspan class="k">{label}</tspan> {dashes}</tspan>'


def build_stat_rows():
    y, gap = 92, 22
    out = []

    rows, y = block_rows(y, gap, ABOUT); out += rows
    out.append(spacer(y)); y += gap

    rows, y = block_rows(y, gap, LANGUAGES); out += rows
    out.append(spacer(y)); y += gap

    rows, y = block_rows(y, gap, HOBBIES); out += rows
    out.append(spacer(y)); y += gap

    out.append(header_rule(y, "Contact")); y += gap
    rows, y = block_rows(y, gap, CONTACT); out += rows
    out.append(spacer(y)); y += gap

    out.append(header_rule(y, "GitHub Stats")); y += gap

    out.append(row(y, "Repos", [
        ("21", "v", "repo_data"),
        (" {Contributed: ", "dots", None),
        ("21", "v", "contrib_data"),
        ("} | Stars: ", "dots", None),
        ("1", "v", "star_data"),
    ], dots_id="repo_data_dots"))
    y += gap

    out.append(row(y, "Commits", [
        ("…", "v", "commit_data"),
        (" | Followers: ", "dots", None),
        ("8", "v", "follower_data"),
    ], dots_id="commit_data_dots"))
    y += gap

    out.append(row(y, "Lines of Code on GitHub", [
        ("…", "v", "loc_data"),
        (" ( ", "dots", None),
        ("…", "add", "loc_add"),
        ("++", "add", None),
        (", ", "dots", None),
        ("…", "del", "loc_del"),
        ("--", "del", None),
        (" )", "dots", None),
    ], dots_id="loc_data_dots"))
    y += gap

    return "\n".join(out), y


def build(theme):
    dark = theme == "dark"
    bg = "#0d1117" if dark else "#ffffff"
    border = "#30363d" if dark else "#d0d7de"
    ascii_fill = "#7d8590" if dark else "#6e7781"
    header_fill = "#e6edf3" if dark else "#1f2328"
    subtitle_fill = "#7d8590" if dark else "#6e7781"
    key_fill = "#58a6ff" if dark else "#0969da"
    val_fill = "#e6edf3" if dark else "#1f2328"
    dots_fill = "#484f58" if dark else "#8c959f"
    add_fill = "#3fb950" if dark else "#1a7f37"
    del_fill = "#f85149" if dark else "#cf222e"
    divider = "#21262d" if dark else "#d8dee4"

    ascii_tspans = "\n".join(
        f'<tspan x="{ASCII_X}" y="{ASCII_Y0 + i * LINE_H}">{line if line.strip() else " "}</tspan>'
        for i, line in enumerate(LINES)
    )

    stat_rows_xml, last_y = build_stat_rows()
    height = max(ASCII_Y0 + ROWS * LINE_H + 24, last_y + 30)

    svg = f'''<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}px" height="{height}px" font-family="SFMono-Regular,Consolas,'Liberation Mono',Menlo,monospace" font-size="{FONT_SIZE}px">
<style>
  .ascii {{ fill: {ascii_fill}; white-space: pre; }}
  .hdr {{ fill: {header_fill}; font-size: 18px; font-weight: 600; }}
  .sub {{ fill: {subtitle_fill}; font-size: 13px; }}
  .k {{ fill: {key_fill}; }}
  .v {{ fill: {val_fill}; }}
  .dots {{ fill: {dots_fill}; }}
  .add {{ fill: {add_fill}; }}
  .del {{ fill: {del_fill}; }}
  .foot {{ fill: {subtitle_fill}; font-size: 11px; font-style: italic; }}
  text, tspan {{ white-space: pre; }}
</style>
<rect width="{WIDTH}px" height="{height}px" fill="{bg}" rx="14"/>
<rect x="0.5" y="0.5" width="{WIDTH - 1}px" height="{height - 1}px" fill="none" stroke="{border}" rx="14"/>

<text class="ascii">
{ascii_tspans}
</text>

<text>
<tspan x="{STAT_X}" y="38" class="hdr">3141roy</tspan><tspan class="sub"> — github card</tspan>
</text>
<line x1="{STAT_X}" y1="52" x2="{WIDTH - 24}" y2="52" stroke="{divider}" stroke-width="1"/>

<text>
{stat_rows_xml}
</text>

<text>
<tspan x="{STAT_X}" y="{height - 16}" class="foot">Last synced: <tspan id="synced_data">pending first sync</tspan></tspan>
</text>
</svg>
'''
    return svg


for theme in ("dark", "light"):
    out = build(theme)
    out_path = REPO_ROOT / f"{theme}_mode.svg"
    with open(out_path, "w") as f:
        f.write(out)
    print("wrote", out_path, len(out), "bytes")

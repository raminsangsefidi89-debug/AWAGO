#!/usr/bin/env python3
"""Generate lightweight placeholder art for the dashboard image slots.

The AWAGO image-generation step (10 curated images) could not run in the
build environment, so this script draws cohesive SVG placeholders and a
procedural logo/favicon set so the dashboard looks complete. If you later
generate the real images (see docs/IMAGE_PROMPTS.md) and drop them into
app/static/img/ with the exact filenames, the dashboard picks them up
automatically (the <img> tags load .webp first and fall back to these SVGs).

Usage:  python scripts/make_placeholder_images.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

IMG_DIR = Path(__file__).resolve().parent.parent / "app" / "static" / "img"

NAVY = "#0B1220"
NAVY2 = "#14213D"
TEAL = "#2DD4BF"
GOLD = "#F5B942"

STYLE_SUFFIX = (
    " Cohesive visual style: modern fintech aesthetic, deep navy and midnight blue base "
    "(#0B1220 to #14213D), teal (#2DD4BF) and warm gold (#F5B942) accents, soft glow, "
    "subtle grid and data-line motifs, clean vector-like 3D-flat illustration, high-end, "
    "minimal, lots of negative space, no text, no letters, no numbers, no watermark, no logos, no people."
)


def svg_header(w: int, h: int, bg: str = NAVY) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img">'
        f'<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{bg}"/><stop offset="100%" stop-color="{NAVY2}"/>'
        f"</linearGradient>"
        f'<radialGradient id="glow" cx="0.5" cy="0.5" r="0.6">'
        f'<stop offset="0%" stop-color="{TEAL}" stop-opacity="0.35"/>'
        f'<stop offset="100%" stop-color="{TEAL}" stop-opacity="0"/>'
        f"</radialGradient></defs>"
        f'<rect width="{w}" height="{h}" fill="url(#bg)"/>'
    )


def grid(w: int, h: int, step: int = 64, opacity: float = 0.12) -> str:
    lines = []
    for x in range(0, w + 1, step):
        lines.append(
            f'<line x1="{x}" y1="0" x2="{x}" y2="{h}" stroke="{TEAL}" stroke-opacity="{opacity}" stroke-width="1"/>'
        )
    for y in range(0, h + 1, step):
        lines.append(
            f'<line x1="0" y1="{y}" x2="{w}" y2="{y}" stroke="{TEAL}" stroke-opacity="{opacity}" stroke-width="1"/>'
        )
    return "".join(lines)


def hero_bg() -> str:
    w, h = 1920, 800
    s = svg_header(w, h) + grid(w, h, 80, 0.10)
    s += '<ellipse cx="520" cy="420" rx="620" ry="360" fill="url(#glow)"/>'
    # candlestick-like bars on the left half
    xs = [120, 200, 280, 360, 440, 520, 600, 680, 760]
    heights = [120, 220, 160, 300, 240, 380, 300, 420, 340]
    for x, hh in zip(xs, heights, strict=False):
        y = 560 - hh
        s += f'<rect x="{x}" y="{y}" width="34" height="{hh}" rx="6" fill="{TEAL}" fill-opacity="0.28"/>'
        s += f'<rect x="{x + 11}" y="{y - 34}" width="12" height="{hh + 68}" rx="6" fill="{TEAL}" fill-opacity="0.5"/>'
    # flowing price curve across the banner
    s += (
        f'<path d="M 60 640 C 320 560, 420 420, 640 430 S 980 320, 1180 360 '
        f'S 1520 260, 1880 220" fill="none" stroke="{TEAL}" stroke-width="5" '
        f'stroke-linecap="round" stroke-opacity="0.9"/>'
    )
    s += (
        f'<path d="M 60 640 C 320 560, 420 420, 640 430 S 980 320, 1180 360 '
        f'S 1520 260, 1880 220 L 1880 800 L 60 800 Z" fill="{TEAL}" fill-opacity="0.08"/>'
    )
    s += (
        f'<path d="M 100 720 C 400 680, 700 700, 1000 640 S 1500 560, 1900 600" '
        f'fill="none" stroke="{GOLD}" stroke-width="3" stroke-dasharray="10 10" stroke-opacity="0.65"/>'
    )
    s += "</svg>"
    return s


def logo_mark() -> str:
    w = h = 1024
    s = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<defs><linearGradient id="tg" x1="0" y1="1" x2="1" y2="0">'
        f'<stop offset="0%" stop-color="{TEAL}"/><stop offset="100%" stop-color="{GOLD}"/></linearGradient></defs>'
    )
    s += '<circle cx="512" cy="512" r="380" fill="none" stroke="url(#tg)" stroke-width="36"/>'
    s += f'<circle cx="512" cy="512" r="300" fill="none" stroke="{TEAL}" stroke-opacity="0.35" stroke-width="10"/>'
    # upward arrow
    s += '<path d="M 320 640 L 512 380 L 704 640" fill="none" stroke="url(#tg)" stroke-width="64" stroke-linecap="round" stroke-linejoin="round"/>'
    s += (
        '<path d="M 512 420 L 512 700" stroke="url(#tg)" stroke-width="64" stroke-linecap="round"/>'
    )
    # wave
    s += (
        f'<path d="M 300 760 C 380 700, 440 820, 512 760 S 660 700, 724 760" '
        f'fill="none" stroke="{TEAL}" stroke-width="40" stroke-linecap="round" stroke-opacity="0.85"/>'
    )
    s += "</svg>"
    return s


def empty_state() -> str:
    w, h = 800, 600
    s = svg_header(w, h) + grid(w, h, 50, 0.08)
    s += f'<rect x="120" y="110" width="560" height="380" rx="22" fill="{NAVY2}" stroke="{TEAL}" stroke-opacity="0.4" stroke-width="3"/>'
    s += f'<line x1="170" y1="380" x2="630" y2="380" stroke="{TEAL}" stroke-opacity="0.5" stroke-width="4" stroke-dasharray="4 14" stroke-linecap="round"/>'
    # magnifier
    s += f'<circle cx="500" cy="270" r="72" fill="none" stroke="{GOLD}" stroke-width="10" stroke-opacity="0.9"/>'
    s += f'<line x1="552" y1="322" x2="612" y2="382" stroke="{GOLD}" stroke-width="14" stroke-linecap="round"/>'
    s += "</svg>"
    return s


def error_state() -> str:
    w, h = 800, 600
    s = svg_header(w, h) + grid(w, h, 50, 0.08)
    s += f'<circle cx="220" cy="300" r="52" fill="{TEAL}" fill-opacity="0.85"/>'
    s += f'<circle cx="580" cy="300" r="52" fill="{TEAL}" fill-opacity="0.85"/>'
    s += f'<line x1="290" y1="290" x2="370" y2="290" stroke="{GOLD}" stroke-width="9" stroke-linecap="round"/>'
    s += f'<line x1="430" y1="310" x2="510" y2="310" stroke="{GOLD}" stroke-width="9" stroke-linecap="round"/>'
    s += f'<line x1="386" y1="252" x2="416" y2="222" stroke="{GOLD}" stroke-width="7" stroke-linecap="round"/>'
    s += f'<line x1="398" y1="340" x2="428" y2="372" stroke="{GOLD}" stroke-width="7" stroke-linecap="round"/>'
    s += f'<line x1="410" y1="296" x2="404" y2="304" stroke="{GOLD}" stroke-width="7" stroke-linecap="round"/>'
    s += "</svg>"
    return s


def training_state() -> str:
    w, h = 800, 600
    s = svg_header(w, h) + grid(w, h, 50, 0.08)
    nodes = [(210, 180), (210, 300), (210, 420), (360, 240), (360, 360), (510, 300)]
    for x, y in nodes:
        s += f'<circle cx="{x}" cy="{y}" r="26" fill="{TEAL}" fill-opacity="0.55" stroke="{TEAL}" stroke-width="3"/>'
    for x1, y1 in nodes[:3]:
        for x2, y2 in nodes[3:5]:
            s += f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{TEAL}" stroke-opacity="0.35" stroke-width="3"/>'
    for x1, y1 in nodes[3:5]:
        s += f'<line x1="{x1}" y1="{y1}" x2="510" y2="300" stroke="{TEAL}" stroke-opacity="0.35" stroke-width="3"/>'
    s += f'<line x1="510" y1="300" x2="620" y2="300" stroke="{GOLD}" stroke-width="5" stroke-dasharray="8 8"/>'
    s += f'<path d="M 620 380 L 670 330 L 710 350 L 760 240" fill="none" stroke="{GOLD}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>'
    s += "</svg>"
    return s


def demo_banner_bg() -> str:
    w, h = 1600, 300
    s = svg_header(w, h, "#241a02")
    for i in range(-300, w + 300, 90):
        s += f'<line x1="{i}" y1="0" x2="{i + 300}" y2="{h}" stroke="{GOLD}" stroke-opacity="0.16" stroke-width="26"/>'
    s += (
        f'<path d="M 0 200 C 200 160, 300 220, 480 180 S 800 120, 1000 170 '
        f'S 1350 210, 1600 150" fill="none" stroke="{NAVY}" stroke-opacity="0.35" '
        f'stroke-width="6" stroke-dasharray="24 18"/>'
    )
    s += "</svg>"
    return s


def card_forecast() -> str:
    w, h = 640, 400
    s = svg_header(w, h) + grid(w, h, 50, 0.10)
    s += f'<path d="M 60 320 L 180 260 L 280 290 L 360 210" fill="none" stroke="{TEAL}" stroke-width="8" stroke-linecap="round"/>'
    s += f'<path d="M 360 210 L 560 140" fill="none" stroke="{GOLD}" stroke-width="8" stroke-dasharray="14 12" stroke-linecap="round"/>'
    s += f'<path d="M 360 210 L 580 60 L 580 320 Z" fill="{GOLD}" fill-opacity="0.16"/>'
    s += "</svg>"
    return s


def card_trend() -> str:
    w, h = 640, 400
    s = svg_header(w, h) + grid(w, h, 50, 0.10)
    s += (
        f'<polyline points="40,320 80,260 120,290 160,200 200,240 240,150 280,190 '
        f'320,120 360,160 400,90 440,130 480,70 520,110 560,60 600,90" '
        f'fill="none" stroke="{TEAL}" stroke-opacity="0.55" stroke-width="5"/>'
    )
    s += f'<line x1="40" y1="330" x2="600" y2="80" stroke="{GOLD}" stroke-width="8" stroke-linecap="round"/>'
    s += f'<path d="M 560 66 L 600 60 L 592 100" fill="none" stroke="{GOLD}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>'
    s += f'<path d="M 40 250 C 140 230, 240 210, 340 180 S 520 120, 600 110" fill="none" stroke="{TEAL}" stroke-width="4" stroke-opacity="0.35"/>'
    s += "</svg>"
    return s


def card_evaluation() -> str:
    w, h = 640, 400
    s = svg_header(w, h) + grid(w, h, 50, 0.10)
    s += f'<path d="M 50 300 C 160 260, 260 250, 360 210 S 540 160, 600 150" fill="none" stroke="{TEAL}" stroke-width="7"/>'
    s += f'<path d="M 50 320 C 160 300, 260 290, 360 260 S 540 230, 600 220" fill="none" stroke="{GOLD}" stroke-width="7" stroke-dasharray="12 10"/>'
    s += f'<rect x="380" y="140" width="150" height="120" rx="12" fill="{NAVY2}" stroke="{TEAL}" stroke-opacity="0.6" stroke-width="3"/>'
    s += f'<line x1="250" y1="80" x2="250" y2="140" stroke="{GOLD}" stroke-width="6"/>'
    s += f'<line x1="190" y1="140" x2="310" y2="140" stroke="{GOLD}" stroke-width="6"/>'
    s += f'<path d="M 190 140 L 165 200 L 215 200 Z" fill="{GOLD}" fill-opacity="0.6"/>'
    s += f'<path d="M 310 140 L 285 200 L 335 200 Z" fill="{GOLD}" fill-opacity="0.6"/>'
    s += "</svg>"
    return s


def og_image() -> str:
    w, h = 1200, 630
    s = svg_header(w, h) + grid(w, h, 60, 0.09)
    s += '<ellipse cx="600" cy="330" rx="420" ry="240" fill="url(#glow)"/>'
    s += f'<circle cx="600" cy="315" r="190" fill="none" stroke="{TEAL}" stroke-opacity="0.55" stroke-width="4"/>'
    for ang in range(0, 360, 30):
        import math

        x1 = 600 + 190 * math.cos(math.radians(ang))
        y1 = 315 + 190 * math.sin(math.radians(ang))
        s += f'<circle cx="{x1:.0f}" cy="{y1:.0f}" r="6" fill="{TEAL}" fill-opacity="0.7"/>'
    s += f'<path d="M 420 380 L 500 320 L 560 340 L 640 260 L 720 290 L 790 220" fill="none" stroke="{GOLD}" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>'
    s += f'<rect x="330" y="180" width="540" height="280" rx="18" fill="{NAVY2}" fill-opacity="0.45" stroke="{TEAL}" stroke-opacity="0.35" stroke-width="3"/>'
    s += "</svg>"
    return s


# ----------------------------------------------------------------------
# Procedural logo + favicons (PNG with alpha) via Pillow
# ----------------------------------------------------------------------


def png_logo_and_favicons() -> None:
    from PIL import Image, ImageDraw

    size = 1024
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def teal_gold(p: float):
        t = (45, 212, 191, 255)
        g = (245, 185, 66, 255)
        return tuple(int(t[i] + (g[i] - t[i]) * p) for i in range(4))

    # compass ring
    d.ellipse([128, 128, 896, 896], outline=teal_gold(0.0), width=36)
    d.ellipse([208, 208, 816, 816], outline=(45, 212, 191, 90), width=10)
    # upward arrow
    d.line([320, 640, 512, 380], fill=teal_gold(0.1), width=64)
    d.line([512, 380, 704, 640], fill=teal_gold(0.8), width=64)
    d.line([512, 420, 512, 700], fill=teal_gold(0.5), width=64)
    # wave
    pts = [(300 + i * 12, 760 + int(46 * __import__("math").sin(i / 4.2))) for i in range(36)]
    d.line(pts, fill=(45, 212, 191, 220), width=40, joint="curve")

    img.save(IMG_DIR / "logo-mark.png")
    img.resize((180, 180), Image.LANCZOS).save(IMG_DIR / "apple-touch-icon-180x180.png")
    img.resize((32, 32), Image.LANCZOS).save(IMG_DIR / "favicon-32x32.png")


# ------------------------------------------------------------------

IMAGES = [
    (
        "hero-bg.webp",
        1920,
        800,
        "Dashboard header/hero background behind a dark gradient overlay.",
        "Wide abstract banner background representing global currency markets: flowing luminous candlestick-like bars and smooth glowing price curves over a faint world-grid, depth of field, calm and professional, leave the center-right area relatively empty for overlay text.",
        hero_bg,
    ),
    (
        "logo-mark.png",
        1024,
        1024,
        "AWAGO emblem in the header, favicon source (32x32 and 180x180 exports).",
        "Minimal abstract emblem for a forecasting platform: a stylized upward-curving arrow blended with a wave and a subtle compass-like ring, geometric, symmetrical, teal and gold gradient on a transparent background, flat vector look, no text.",
        logo_mark,
    ),
    (
        "empty-state.webp",
        800,
        600,
        "Shown when no data is available for the selected pair/range.",
        "Illustration of an empty chart panel: a clean dashboard frame with a faint dotted baseline and a small magnifying glass hovering over blank space, soft glow, friendly and calm mood.",
        empty_state,
    ),
    (
        "error-state.webp",
        800,
        600,
        "Shown on API/network errors.",
        "Illustration of a disconnected data link: two glowing nodes with a gently broken connecting line and small sparks, a subtle warning-amber accent, calm rather than alarming, tidy composition.",
        error_state,
    ),
    (
        "training-state.webp",
        800,
        600,
        "Shown while a model training or data collection job is running.",
        "Illustration of a machine-learning model being trained: layered translucent neural-network nodes connected by glowing lines feeding into a rising line chart, sense of motion and progress.",
        training_state,
    ),
    (
        "demo-banner-bg.webp",
        1600,
        300,
        "Background of the prominent Demo-data banner, under a semi-transparent overlay.",
        "Wide thin strip pattern in amber and navy: diagonal soft hatching with faint broken chart lines, indicating a simulated environment, subtle, low contrast, seamless feel.",
        demo_banner_bg,
    ),
    (
        "card-forecast.webp",
        640,
        400,
        "Illustration for the forecast feature card.",
        "A smooth price line that continues into the future as a dashed glowing path, surrounded by a translucent widening cone representing uncertainty, on a dark grid.",
        card_forecast,
    ),
    (
        "card-trend.webp",
        640,
        400,
        "Illustration for the trend-analysis feature card.",
        "A noisy price series with a clean bright trend line cutting through it and a subtle directional arrow, layered moving-average ribbons in teal and gold, dark grid.",
        card_trend,
    ),
    (
        "card-evaluation.webp",
        640,
        400,
        "Illustration for the model-evaluation feature card.",
        "Two competing glowing curves, one labeled-by-color as the model and one as the baseline, with a magnified comparison zone and a small balance-scale motif, dark grid, no text.",
        card_evaluation,
    ),
    (
        "og-image.webp",
        1200,
        630,
        "Social preview (Open Graph / Twitter card) referenced in the HTML head.",
        "Cinematic wide composition of a futuristic currency analytics dashboard floating in space: glowing charts, forecast bands, and a faint globe made of data points, centered focal point with generous margins, no text.",
        og_image,
    ),
]


def main() -> int:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    today = date.today().isoformat()

    for filename, w, h, purpose, prompt, draw in IMAGES:
        stem = filename.rsplit(".", 1)[0]
        svg_name = f"{stem}.svg"
        (IMG_DIR / svg_name).write_text(draw(), encoding="utf-8")

        entry = {
            "filename": filename,
            "placeholder_filename": svg_name,
            "dimensions": f"{w}x{h}",
            "purpose": purpose,
            "prompt": prompt + STYLE_SUFFIX,
            "generation_date": None,
            "status": "fallback-placeholder",
            "note": (
                "Image generation was unavailable in the build environment "
                "(see docs/IMAGE_PROMPTS.md). The dashboard loads the .webp/.png "
                "file first and falls back to the SVG placeholder automatically."
            ),
            "recorded_on": today,
        }
        if filename == "logo-mark.png":
            entry["status"] = "fallback-placeholder-png"
            entry["generation_date"] = today
        manifest.append(entry)
        print(f"  wrote {svg_name}")

    png_logo_and_favicons()
    print("  wrote logo-mark.png, favicon-32x32.png, apple-touch-icon-180x180.png")

    (IMG_DIR / "manifest.json").write_text(
        json.dumps(
            {"images": manifest, "image_limit": 10, "generated_count": 0},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print("  wrote manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build the Slovenia photo album.

Layout
------
photos/
  day-01-ljubljana/
    day.json          optional: title, date, note, captions
    01-dragon-bridge.jpg
    02-castle-view.jpg
  day-02-lake-bled/
    ...

Each folder in photos/ becomes one tab. Folders and photos are sorted
naturally, so prefix names with numbers to control the order.

day.json (all keys optional)
----------------------------
{
  "title": "Ljubljana",
  "date": "2026-09-14",
  "note": "A short intro shown above the photos.",
  "captions": {
    "01-dragon-bridge.jpg": "Crossing the Dragon Bridge at sunrise."
  }
}

Usage
-----
    python build_album.py                      # writes ./site/index.html
    python build_album.py --out public
    python build_album.py --title "Slovenia" --subtitle "September 2026"

Pillow is optional but recommended: it makes web-sized copies of your photos
(and thumbnails), fixes rotation, and drops EXIF data such as GPS location.
Your originals in photos/ are never modified.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

try:
    from PIL import Image, ImageOps

    RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS
except ImportError:  # Pillow missing: fall back to copying originals
    Image = None
    ImageOps = None
    RESAMPLE = None

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF = True
except ImportError:
    HEIF = False

ROOT = Path(__file__).resolve().parent
EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}
if Image is not None and HEIF:
    EXTS |= {".heic", ".heif"}

FULL_MAX = 2200  # longest edge of the lightbox image
THUMB_MAX = 900  # longest edge of the grid image


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def natural_key(text: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        sys.exit(f"error: {path} is not valid JSON ({err})")


def esc(value) -> str:
    return html.escape(str(value), quote=True)


CAMERA_NAME = re.compile(
    r"^(img|dsc|dscn|dscf|pxl|mvimg|dji|photo|image|p)[-_ ]*\d.*$|^\d[\d_ -]*$", re.I
)


def auto_caption(stem: str) -> str:
    """Turn '03-dragon-bridge' into 'Dragon bridge'; ignore camera file names."""
    cleaned = re.sub(r"^\d+[-_ ]+", "", stem).replace("-", " ").replace("_", " ").strip()
    if not cleaned or CAMERA_NAME.match(cleaned):
        return ""
    return cleaned[0].upper() + cleaned[1:]


def format_date(value: str) -> str:
    if not value:
        return ""
    try:
        d = date.fromisoformat(value)
    except ValueError:
        return value
    return f"{d:%A}, {d:%B} {d.day}, {d.year}"


def folder_title(name: str) -> str:
    rest = re.sub(r"^day[-_ ]*\d+[-_ ]*", "", name, flags=re.I)
    return rest.replace("-", " ").replace("_", " ").strip().title()


def folder_number(name: str, index: int) -> int:
    m = re.match(r"day[-_ ]*(\d+)", name, re.I)
    return int(m.group(1)) if m else index + 1


# --------------------------------------------------------------------------
# images
# --------------------------------------------------------------------------
def publish_photo(src: Path, out_dir: Path, used: set[str]):
    """Write the web versions of one photo. Returns (name, width, height)."""
    (out_dir / "thumbs").mkdir(parents=True, exist_ok=True)

    def unique(name: str) -> str:
        base, dot, ext = name.rpartition(".")
        candidate, n = name, 2
        while candidate.lower() in used:
            candidate = f"{base}-{n}.{ext}"
            n += 1
        used.add(candidate.lower())
        return candidate

    if Image is not None and src.suffix.lower() != ".gif":
        try:
            with Image.open(src) as opened:
                im = ImageOps.exif_transpose(opened)
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                width, height = im.size
                name = unique(f"{src.stem}.jpg")

                full = im.copy()
                full.thumbnail((FULL_MAX, FULL_MAX), RESAMPLE)
                full.save(out_dir / name, "JPEG", quality=82, optimize=True, progressive=True)

                thumb = im.copy()
                thumb.thumbnail((THUMB_MAX, THUMB_MAX), RESAMPLE)
                thumb.save(
                    out_dir / "thumbs" / name, "JPEG", quality=78, optimize=True, progressive=True
                )
                return name, width, height
        except Exception as err:  # noqa: BLE001 - keep building, just copy the original
            print(f"  warning: could not resize {src.name} ({err}); copying original")

    name = unique(src.name)
    shutil.copy2(src, out_dir / name)
    shutil.copy2(src, out_dir / "thumbs" / name)
    width = height = 0
    if Image is not None:
        try:
            with Image.open(src) as opened:
                width, height = opened.size
        except Exception:  # noqa: BLE001
            pass
    return name, width, height


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
def render_photo(photo: dict, position: int, alt_prefix: str) -> str:
    w, h = photo["w"], photo["h"]
    ratio = round(w / h, 4) if w and h else 1.5
    dims = f' width="{w}" height="{h}"' if w and h else ""
    alt = photo["caption"] or f"{alt_prefix}, photo {position}"
    caption = f"<figcaption>{esc(photo['caption'])}</figcaption>" if photo["caption"] else ""
    return (
        f'<figure class="ph" style="--r:{ratio}">'
        f'<a href="{esc(photo["full"])}">'
        f'<img src="{esc(photo["thumb"])}" alt="{esc(alt)}"{dims} loading="lazy" decoding="async">'
        f"</a>{caption}</figure>"
    )


def render_day(day: dict) -> tuple[str, str]:
    slug = day["slug"]
    title_span = f"<span>{esc(day['title'])}</span>" if day["title"] else ""
    tab = (
        f'<a role="tab" id="tab-{slug}" href="#{slug}" aria-controls="panel-{slug}" '
        f'aria-selected="false" tabindex="-1"><b>{esc(day["label"])}</b>{title_span}</a>'
    )

    line = f"<h2>{esc(day['title'] or day['label'])}</h2>"
    if day["date"]:
        line += f'<p class="date">{esc(day["date"])}</p>'
    head = [f'<div class="day-line">{line}</div>']
    if day["note"]:
        head.append(f'<p class="note">{esc(day["note"])}</p>')

    alt_prefix = day["title"] or day["label"]
    photos = "".join(
        render_photo(p, i, alt_prefix) for i, p in enumerate(day["photos"], start=1)
    )
    panel = (
        f'<section class="day" id="panel-{slug}" role="tabpanel" '
        f'aria-labelledby="tab-{slug}" hidden>'
        f'<header class="day-head">{"".join(head)}</header>'
        f'<div class="grid">{photos}</div></section>'
    )
    return tab, panel


def build(args) -> None:
    config = load_json(ROOT / "album.json", {})
    title = args.title or config.get("title") or "Photo album"
    subtitle = args.subtitle if args.subtitle is not None else config.get("subtitle", "")
    use_auto = bool(config.get("auto_captions", True))

    photos_dir = (ROOT / args.photos).resolve()
    out = Path(args.out)
    out = (out if out.is_absolute() else ROOT / out).resolve()

    if not photos_dir.is_dir():
        sys.exit(f"error: photos folder not found: {photos_dir}")
    if out == ROOT or out == photos_dir or ROOT.is_relative_to(out) or photos_dir.is_relative_to(out):
        sys.exit(f"error: refusing to use {out} as the output folder")

    if Image is None:
        print("note: Pillow not installed - photos will be copied as-is (pip install pillow)")

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    day_dirs = sorted(
        (d for d in photos_dir.iterdir() if d.is_dir() and not d.name.startswith(".")),
        key=lambda d: natural_key(d.name),
    )

    days = []
    total = 0
    for index, folder in enumerate(day_dirs):
        meta = load_json(folder / "day.json", {})
        captions = meta.get("captions", {}) or {}
        files = sorted(
            (
                f
                for f in folder.iterdir()
                if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in EXTS
            ),
            key=lambda f: natural_key(f.name),
        )

        known = {f.name for f in files} | {f.stem for f in files}
        for key in captions:
            if key not in known:
                print(f"  warning: {folder.name}/day.json has a caption for '{key}' but no such photo")

        if not files:
            print(f"skipping {folder.name}: no photos yet")
            continue

        print(f"{folder.name}: {len(files)} photo(s)")
        number = folder_number(folder.name, index)
        out_dir = out / "photos" / folder.name
        used: set[str] = set()
        photos = []
        for f in files:
            name, w, h = publish_photo(f, out_dir, used)
            caption = captions.get(f.name) or captions.get(f.stem) or ""
            if not caption and use_auto:
                caption = auto_caption(f.stem)
            base = f"photos/{quote(folder.name)}"
            photos.append(
                {
                    "full": f"{base}/{quote(name)}",
                    "thumb": f"{base}/thumbs/{quote(name)}",
                    "w": w,
                    "h": h,
                    "caption": caption,
                }
            )
        total += len(photos)
        days.append(
            {
                "slug": f"day-{number:02d}" if re.match(r"day", folder.name, re.I) else re.sub(r"[^a-z0-9]+", "-", folder.name.lower()).strip("-"),
                "label": meta.get("label") or f"Day {number}",
                "title": meta.get("title") if "title" in meta else folder_title(folder.name),
                "date": format_date(meta.get("date", "")),
                "note": meta.get("note", ""),
                "photos": photos,
            }
        )

    # slugs must be unique
    seen: dict[str, int] = {}
    for day in days:
        n = seen.get(day["slug"], 0) + 1
        seen[day["slug"]] = n
        if n > 1:
            day["slug"] = f"{day['slug']}-{n}"

    if days:
        rendered = [render_day(d) for d in days]
        tabs_html = "".join(t for t, _ in rendered)
        panels_html = "".join(p for _, p in rendered)
    else:
        tabs_html = ""
        panels_html = '<p class="empty">No photos yet. Add images to a folder inside photos/ and push again.</p>'

    page = (
        TEMPLATE.replace("@@TITLE@@", esc(title))
        .replace("@@SUBTITLE@@", f'<p class="sub">{esc(subtitle)}</p>' if subtitle else "")
        .replace("@@TABS@@", tabs_html)
        .replace("@@PANELS@@", panels_html)
    )
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"built {len(days)} day(s), {total} photo(s) -> {out / 'index.html'}")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>@@TITLE@@</title>
<meta name="description" content="@@TITLE@@ - a photo album, one tab per day.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600&display=swap">
<style>
:root{--paper:#ffffff;--ink:#1b1b1a;--muted:#6f6f6a;--line:#e6e6e2;--wash:#f1f1ee;--row:240px;--pad:24px}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:400 15px/1.5 "Hanken Grotesk",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
body:has(dialog[open]){overflow:hidden}
.wrap{max-width:1440px;margin:0 auto;padding:0 var(--pad)}

.site{padding:40px 0 22px}
h1{margin:0;font-size:22px;font-weight:600;letter-spacing:-.01em;line-height:1.2}
.sub{margin:4px 0 0;color:var(--muted);font-size:14px}

.bar{position:sticky;top:0;z-index:5;background:var(--paper);border-bottom:1px solid var(--line)}
[role=tablist]{display:flex;gap:26px;overflow-x:auto;scrollbar-width:none}
[role=tablist]::-webkit-scrollbar{display:none}
[role=tab]{flex:none;padding:14px 0 12px;font-size:13px;color:var(--muted);text-decoration:none;white-space:nowrap;box-shadow:inset 0 -2px 0 transparent}
[role=tab] b{font-weight:600}
[role=tab] span{margin-left:7px}
[role=tab]:hover{color:var(--ink)}
[role=tab][aria-selected=true]{color:var(--ink);box-shadow:inset 0 -2px 0 var(--ink)}
[role=tab]:focus-visible{outline:2px solid var(--ink);outline-offset:-2px}

.day{padding:28px 0 72px}
.day-head{margin-bottom:24px}
.day-line{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 16px}
.day-line h2{margin:0;font-size:15px;font-weight:600}
.date{margin:0;color:var(--muted);font-size:13px}
.note{margin:6px 0 0;max-width:62ch}
.empty{padding:48px 0;color:var(--muted)}

.grid{display:flex;flex-wrap:wrap;gap:20px 6px}
.grid::after{content:"";flex:999 1 0}
.ph{margin:0;min-width:0;flex:var(--r) 1 calc(var(--r) * var(--row))}
.ph a{display:block;background:var(--wash);line-height:0;cursor:zoom-in}
.ph a:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
.ph img{display:block;width:100%;height:auto;aspect-ratio:var(--r)}
.ph figcaption{margin-top:6px;font-size:13px;line-height:1.4;color:var(--muted)}

dialog#lb{width:100vw;height:100vh;height:100dvh;max-width:none;max-height:none;margin:0;padding:8px var(--pad);border:0;background:var(--paper);color:var(--ink)}
dialog#lb[open]{display:flex;flex-direction:column;gap:6px}
#lb img{flex:1;min-height:0;width:100%;object-fit:contain}
.lb-row{display:flex;justify-content:space-between;align-items:center;gap:16px;font-size:13px}
.lb-row.bottom{align-items:flex-start}
.count{color:var(--muted)}
.cap{margin:0;padding-top:10px;max-width:70ch;font-size:14px;min-height:1.4em}
.lb-nav{display:flex;gap:4px;flex:none}
#lb button{font:inherit;font-size:13px;background:none;border:0;color:var(--ink);padding:10px 8px;cursor:pointer;text-decoration:underline;text-underline-offset:3px}
#lb button:focus-visible{outline:2px solid var(--ink);outline-offset:-2px}

@media (max-width:640px){:root{--row:200px;--pad:16px}.site{padding-top:28px}}
</style>
<noscript><style>[role=tabpanel][hidden]{display:block}</style></noscript>
</head>
<body>
<header class="site"><div class="wrap"><h1>@@TITLE@@</h1>@@SUBTITLE@@</div></header>
<div class="bar"><div class="wrap"><div role="tablist" aria-label="Days">@@TABS@@</div></div></div>
<main class="wrap">@@PANELS@@</main>

<dialog id="lb" aria-label="Photo viewer">
  <div class="lb-row"><span class="count"></span><button type="button" class="close">Close</button></div>
  <img alt="">
  <div class="lb-row bottom">
    <p class="cap"></p>
    <div class="lb-nav"><button type="button" class="prev">Previous</button><button type="button" class="next">Next</button></div>
  </div>
</dialog>

<script>
(function () {
  var tabs = Array.prototype.slice.call(document.querySelectorAll('[role=tab]'));
  var panels = Array.prototype.slice.call(document.querySelectorAll('[role=tabpanel]'));
  if (tabs.length) {
    var ids = tabs.map(function (t) { return t.getAttribute('href').slice(1); });
    var current = function () { return Math.max(0, ids.indexOf(location.hash.slice(1))); };
    var show = function (i) {
      tabs.forEach(function (t, k) {
        t.setAttribute('aria-selected', k === i ? 'true' : 'false');
        t.tabIndex = k === i ? 0 : -1;
      });
      panels.forEach(function (p, k) { p.hidden = k !== i; });
      tabs[i].scrollIntoView({ inline: 'center', block: 'nearest' });
    };
    window.addEventListener('hashchange', function () { show(current()); window.scrollTo(0, 0); });
    tabs.forEach(function (t, i) {
      t.addEventListener('keydown', function (e) {
        var target = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
        if (target === undefined) return;
        e.preventDefault();
        var n = (target + tabs.length) % tabs.length;
        location.hash = ids[n];
        tabs[n].focus();
      });
    });
    show(current());
  }

  var dlg = document.getElementById('lb');
  if (!dlg || typeof dlg.showModal !== 'function') return;
  var img = dlg.querySelector('img');
  var cap = dlg.querySelector('.cap');
  var count = dlg.querySelector('.count');
  var list = [], idx = 0;

  function render() {
    var a = list[idx], thumb = a.querySelector('img'), fc = a.parentNode.querySelector('figcaption');
    img.src = a.getAttribute('href');
    img.alt = thumb.alt;
    cap.textContent = fc ? fc.textContent : '';
    count.textContent = (idx + 1) + ' of ' + list.length;
    var next = new Image();
    next.src = list[(idx + 1) % list.length].getAttribute('href');
  }
  function step(d) { idx = (idx + d + list.length) % list.length; render(); }

  document.addEventListener('click', function (e) {
    var a = e.target.closest ? e.target.closest('.ph a') : null;
    if (!a) return;
    e.preventDefault();
    list = Array.prototype.slice.call(a.closest('.grid').querySelectorAll('.ph a'));
    idx = list.indexOf(a);
    render();
    dlg.showModal();
  });
  dlg.querySelector('.prev').addEventListener('click', function () { step(-1); });
  dlg.querySelector('.next').addEventListener('click', function () { step(1); });
  dlg.querySelector('.close').addEventListener('click', function () { dlg.close(); });
  dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
  dlg.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
  });
  var x0 = null;
  img.addEventListener('touchstart', function (e) { x0 = e.changedTouches[0].clientX; }, { passive: true });
  img.addEventListener('touchend', function (e) {
    if (x0 === null) return;
    var dx = e.changedTouches[0].clientX - x0;
    x0 = null;
    if (Math.abs(dx) > 50) step(dx < 0 ? 1 : -1);
  });
})();
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the tabbed photo album.")
    parser.add_argument("--photos", default="photos", help="folder with one sub-folder per day")
    parser.add_argument("--out", default="site", help="output folder (deleted and recreated)")
    parser.add_argument("--title", help="override the title from album.json")
    parser.add_argument("--subtitle", help="override the subtitle from album.json")
    build(parser.parse_args())


if __name__ == "__main__":
    main()

# Slovenia Photo Album

A minimal photo album with one tab per day and an optional caption on every photo. It builds automatically with GitHub Actions and deploys to GitHub Pages.

## How it works

```
repo/
├── photos/
│   ├── day-01-ljubljana/
│   │   ├── day.json              ← title, date, intro note, captions
│   │   ├── 01-dragon-bridge.jpg
│   │   └── 02-castle-view.jpg
│   ├── day-02-lake-bled/
│   ├── day-03-lake-bohinj/
│   └── day-04-triglav/
├── album.json                    ← album title and subtitle
├── build_album.py                ← scans photos/ and writes site/index.html
└── .github/workflows/build-album.yml
```

Each folder inside `photos/` becomes a tab. Every push to `main` that touches `photos/`, `album.json` or `build_album.py` builds the site and deploys it. The four day folders are placeholders: rename them, add or delete folders, and change the titles to match your trip. Folders with no photos are skipped, so empty days never show up as tabs.

## Setup (one time)

1. Create a repo on GitHub and push these files to the `main` branch.
2. In the repo, go to **Settings → Pages → Source** and choose **GitHub Actions**.
3. Add photos to the day folders, commit, and push.

The site appears at `https://<your-username>.github.io/<repo-name>/` after the first run finishes (check the **Actions** tab).

## Adding captions

Put a `day.json` in each day folder. Every key is optional.

```json
{
  "title": "Ljubljana",
  "date": "2026-09-14",
  "note": "A short intro shown above the day's photos.",
  "captions": {
    "01-dragon-bridge.jpg": "The Dragon Bridge, early morning.",
    "04-market-stalls": "You can leave off the extension too."
  }
}
```

- `date` in `YYYY-MM-DD` form is shown as "Monday, September 14, 2026". Any other text is shown as written.
- `label` (optional) replaces the tab's "Day 1" text.
- Photos without a caption get one from the file name: `03-triple-bridge.jpg` becomes "Triple bridge". Camera names like `IMG_4021.jpg` or `PXL_2026...` are ignored. To turn this off, set `"auto_captions": false` in `album.json`.
- If a caption key doesn't match any photo, the build prints a warning, which helps catch typos.

## Ordering

Days and photos are sorted by name, with numbers compared as numbers. Prefix names with `01-`, `02-`, and so on to control the order. Unnumbered files sort after numbered ones.

## What the build does to your photos

Your originals in `photos/` are never changed. The build writes web copies into `site/`:

- a 2200 px version for the full-size viewer and a 900 px thumbnail for the grid
- rotation fixed from the camera's orientation data
- EXIF data (including GPS location) is not carried over to the published copies
- iPhone `.heic` photos are converted automatically (the workflow installs `pillow-heif`)

Because only the resized copies are published, a repo full of full-resolution photos stays fast to load. Keep the originals' total size in mind though: GitHub recommends repos stay under about 1 GB.

## Run it locally

```
pip install pillow pillow-heif
python build_album.py
```

Then open `site/index.html` in your browser. Useful options:

```
python build_album.py --title "Slovenia" --subtitle "September 2026"
python build_album.py --out public
```

## Using the album

- Click a tab (or use the left and right arrow keys while a tab is focused) to switch days. The address updates, so `#day-02` links straight to Day 2.
- Click a photo to open it larger. Use Previous and Next, the arrow keys, or swipe on a phone. Press Esc to close.

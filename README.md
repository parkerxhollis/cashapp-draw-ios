# CashDraw iOS

Draw custom designs on your **Cash App card** using iPhone Mirroring on macOS.

Uses raw CGEvent (HID-level) for precise pixel-by-pixel mouse drags that translate through iPhone Mirroring as touch strokes. Built from the same proven engine as [RevoDraw iOS](https://github.com/parkerxhollis/revo-draw-ios).

## How It Works

```
Your design (PNG) → calibrate.py (map card area) → draw.py (CGEvent drags) → iPhone Mirroring → Cash App
```

1. **Calibrate** — click the four corners of the drawing area once
2. **Create a template** — black=draw, red=no-go, white=skip
3. **Draw** — the script drags the mouse pixel by pixel

## Differences from Revolut

- **Clean rectangular canvas** — no L-shape logo cutouts, easier to design for
- **Fixed pen thickness** — Cash App doesn't offer size control, so no "set pen size" step
- **Larger drawing area** — template is 200px wide (vs 150px for Revolut) for more detail

## Requirements

- macOS Sequoia 15+ with iPhone Mirroring
- Python 3.11+
- Cash App with a customizable card
- **Accessibility permission** for Terminal (System Settings → Privacy & Security → Accessibility)

## Setup

```bash
git clone https://github.com/parkerxhollis/cashapp-draw-ios.git
cd cashapp-draw-ios
pip install -r requirements.txt
```

> **Note:** PyObjC (the `Quartz` framework) is bundled with macOS Python. If your virtual environment doesn't have it: `pip install pyobjc-framework-Quartz`

## Usage

### 1. Calibrate (one-time setup)

Open Cash App → Card → Design Card → **Draw tool**. Then:

```bash
python calibrate.py --manual
```

Click the four corners of the drawing area when prompted. Saves `config.json`.

### 2. Create your design

```bash
python draw.py --template
```

Creates `template.png` sized to your card's exact proportions. Edit it in any image editor:

| Color | Meaning |
|---|---|
| **Black** | Draw on card |
| **Red** | No-go zone — never draw here |
| **White** | Skip (background) |

The canvas is a clean rectangle — no auto-marked cutoffs. Add a thin red border around edges if clicking outside kicks you out of the drawing tool.

### 3. Draw

Two modes:

```bash
# Precise — individual drags per pixel. Consistent coverage.
python draw.py design.png --mode tiny

# Fast — row-by-row continuous swipes. Good for bold designs.
python draw.py design.png --mode strokes

# Preview first:
python draw.py design.png --mode tiny --dry-run
```

The script pauses for you to confirm before starting.

### Verify calibration

```bash
python draw.py design.png --show-bounds
```

Moves the mouse to each corner of your calibrated area.

### Test mode

```bash
python draw.py design.png --mode test
```

Draws a big X — confirms CGEvent plumbing works.

## Tips

- **Start with `--dry-run`** to see pixel/drag counts
- **`--mode tiny`** gives the most consistent results
- **`--mode strokes`** is faster but line weight varies slightly
- Cash App's fixed pen is thicker than Revolut's smallest setting — designs with some breathing room work best
- Use `--delay 0.05` to slow things down if the app seems to miss strokes
- Keep the Mirroring window in the same position between calibration and drawing

## Template Design Guide

- Template resolution is **200 pixels wide**, height auto-computed from your card's aspect ratio
- Black = the script draws here (R/G/B < 128 threshold)
- Red = no-go zone (R>200, G<80, B<80). Paint red around edges to avoid accidental clicks outside the canvas
- White = skipped background
- The script reports: "Drawable pixels: 1204 (red no-go: 0)"

## Troubleshooting

| Problem | Fix |
|---|---|
| config.json not found | Run `python calibrate.py --manual` |
| Nothing drawn on card | Make sure the Draw tool is selected in Cash App |
| Cursor moves but no marks | Run `--mode test` to verify CGEvent works. Check Accessibility permissions |
| Clicking outside canvas | Add red no-go zones around the edges of your template |
| Misaligned drawing | Recalibrate — don't move the Mirroring window |
| `ModuleNotFoundError: No module named 'Quartz'` | `pip install pyobjc-framework-Quartz` |

## License

MIT
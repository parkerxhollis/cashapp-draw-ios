#!/usr/bin/env python3
"""
CashDraw iOS — Draw custom designs on your Cash App card via iPhone Mirroring.

Uses raw CGEvent (HID-level) for mouse drags — the only method proven to
work through iPhone Mirroring's touch-event forwarding.

Drawing modes:
  --mode strokes   Row-by-row continuous swipes (fast)
  --mode tiny      Individual pixel drags (precise, consistent coverage)
  --mode test      Draw a big X to verify calibration and event plumbing

Quick start:
    python calibrate.py --manual     # one-time setup
    python draw.py --template        # generate blank template
    python draw.py design.png --mode tiny --dry-run
    python draw.py design.png --mode tiny
"""

import sys
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image
import Quartz  # macOS Core Graphics — bundled with PyObjC (preinstalled on macOS)

# ── Constants ──

DESIGN_COLS = 200  # Cash App canvas is larger, 200px wide gives great detail


# ── CGEvent mouse primitives (HID-level — works through iPhone Mirroring) ──

def cg_move(x: int, y: int):
    """Move mouse cursor to absolute screen position."""
    ev = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (x, y), 0)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def cg_down(x: int, y: int):
    """Left mouse button down at position."""
    ev = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, (x, y), 0)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def cg_up(x: int, y: int):
    """Left mouse button up at position."""
    ev = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, (x, y), 0)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def cg_drag_step(x: int, y: int):
    """Post a single drag-move event (must be called between down and up)."""
    ev = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDragged, (x, y), 0)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def cg_drag(x1: int, y1: int, x2: int, y2: int, steps: int = 10, duration: float = 0.15):
    """Perform a full drag from (x1,y1) to (x2,y2) with step-by-step movement."""
    cg_move(x1, y1)
    time.sleep(0.03)
    cg_down(x1, y1)
    time.sleep(0.05)
    for i in range(1, steps + 1):
        t = i / steps
        cx = int(x1 + (x2 - x1) * t)
        cy = int(y1 + (y2 - y1) * t)
        cg_drag_step(cx, cy)
        time.sleep(duration / steps)
    time.sleep(0.03)
    cg_up(x2, y2)


def cg_screen_size() -> tuple[int, int]:
    """Get primary display dimensions."""
    bounds = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
    return (int(bounds.size.width), int(bounds.size.height))


# ── Helpers ──

def compute_rows(boundary: dict, cols: int = DESIGN_COLS) -> int:
    """Compute grid rows so the design matches the card's actual aspect ratio."""
    bw = boundary["right_x"] - boundary["left_x"]
    bh = boundary["bottom_y"] - boundary["top_y"]
    return max(1, int(cols * bh / bw))


def countdown(seconds: int = 3):
    """Print a countdown and wait."""
    for i in range(seconds, 0, -1):
        print(f"  {i}...")
        time.sleep(1)


def wait_for_enter():
    """Prompt user to confirm before drawing begins."""
    print("\n⚠️  Open Cash App → Card → Design Card → Draw tool")
    input("Press Enter to start...")
    countdown()


# ── Config loading ──

def load_config(config_path: str = "config.json") -> dict:
    """Load calibration config. Exits with a helpful message if missing."""
    if not Path(config_path).exists():
        print(f"Error: {config_path} not found. Run: python calibrate.py --manual")
        sys.exit(1)
    try:
        with open(config_path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: {config_path} is corrupted ({e}). Delete it and re-run calibrate.py.")
        sys.exit(1)


def load_boundary(config: dict) -> dict:
    """Extract and validate the boundary from config."""
    if "boundary" not in config:
        print("Error: config.json is missing 'boundary'. Re-run calibrate.py --manual")
        sys.exit(1)
    return dict(config["boundary"])


# ── Image loading ──

def load_image(image_path: str, cols: int, rows: int) -> tuple[np.ndarray, np.ndarray]:
    """Load and classify a design image.

    Returns (draw_mask, no_go_mask) — both boolean 2D arrays.
      - Black pixels  (R<128, G<128, B<128) → draw_mask = True
      - Red pixels    (R>200, G<80,  B<80)  → no_go_mask = True
      - Everything else                      → skip (white/transparent areas)
    """
    img = Image.open(image_path).convert("RGB")
    img = img.resize((cols, rows), Image.LANCZOS)
    arr = np.array(img)

    draw_mask = np.all(arr < 128, axis=2)
    no_go_mask = (arr[:, :, 0] > 200) & (arr[:, :, 1] < 80) & (arr[:, :, 2] < 80)

    return draw_mask, no_go_mask


# ── Coordinate mapping ──

def pixel_to_screen(col: int, row: int, boundary: dict, cols: int, rows: int) -> tuple[int, int]:
    """Map a design-grid pixel (col, row) to absolute screen coordinates."""
    bw = boundary["right_x"] - boundary["left_x"]
    bh = boundary["bottom_y"] - boundary["top_y"]
    x = int(boundary["left_x"] + (col + 0.5) * bw / cols)
    y = int(boundary["top_y"] + (row + 0.5) * bh / rows)
    return (x, y)


def should_skip(col: int, row: int, no_go_mask: np.ndarray) -> bool:
    """True if pixel should NOT be drawn — red no-go zone."""
    return no_go_mask[row, col]


# ── Stroke extraction ──

def extract_strokes(draw_mask: np.ndarray, no_go_mask: np.ndarray,
                    cols: int, rows: int) -> list[list[tuple[int, int]]]:
    """Convert mask to continuous horizontal strokes (start, end) in screen coords.

    Alternates direction per row for efficient drawing (snake pattern).
    """
    strokes = []
    for row in range(rows):
        inverted_row = rows - 1 - row if row % 2 == 0 else row
        col = 0
        while col < cols:
            if draw_mask[inverted_row, col] and not should_skip(col, inverted_row, no_go_mask):
                start = col
                while col < cols and draw_mask[inverted_row, col] and not should_skip(col, inverted_row, no_go_mask):
                    col += 1
                end = col - 1
                if start < end:
                    # strokes use screen coords directly — resolve at draw time
                    strokes.append((inverted_row, start, end))
            else:
                col += 1
    return strokes


def extract_tiny_drags(draw_mask: np.ndarray, no_go_mask: np.ndarray,
                       cols: int, rows: int) -> list[tuple[int, int]]:
    """Convert mask to individual pixels to draw — one short drag per black pixel.

    Returns list of (col, row) grid positions. Screen coordinates resolved at draw time.
    """
    drags = []
    for row in range(rows):
        for col in range(cols):
            if draw_mask[row, col] and not should_skip(col, row, no_go_mask):
                drags.append((col, row))
    return drags


# ── Drawing (CGEvent-based) ──

def draw_strokes(strokes: list, boundary: dict, cols: int, rows: int,
                 delay: float = 0.02):
    """Draw using CGEvent drags — one per stroke."""
    total = len(strokes)
    if total == 0:
        print("No strokes to draw.")
        return

    print(f"Drawing {total} strokes...")
    sw, _ = cg_screen_size()
    safe_x, safe_y = sw // 2, 50
    start_time = time.time()

    bw = boundary["right_x"] - boundary["left_x"]
    drag_len = max(6, int(bw / cols * 3))

    for i, (row, start_col, end_col) in enumerate(strokes):
        x1, y1 = pixel_to_screen(start_col, row, boundary, cols, rows)
        x2, y2 = pixel_to_screen(end_col, row, boundary, cols, rows)

        dist = max(abs(x2 - x1), abs(y2 - y1))
        steps = max(10, int(dist / 3))
        cg_drag(x1, y1, x2, y2, steps=steps, duration=max(0.08, dist * 0.002))
        time.sleep(delay)

        if (i + 1) % 50 == 0:
            cg_move(safe_x, safe_y)
            time.sleep(0.2)
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            remaining = total - (i + 1)
            eta = remaining / rate
            pct = (i + 1) / total * 100
            print(f"  {i + 1}/{total} ({pct:.0f}%) | {elapsed:.0f}s elapsed | ~{eta:.0f}s left")

    cg_move(safe_x, safe_y)
    total_time = time.time() - start_time
    print(f"  Done: {total} strokes in {total_time:.0f}s")


def draw_tiny_drags(drags: list[tuple[int, int]], boundary: dict, cols: int, rows: int,
                    delay: float = 0.03):
    """Draw individual pixel drags using CGEvent."""
    total = len(drags)
    if total == 0:
        print("No drags to draw.")
        return

    est = total * (delay + 0.12)
    print(f"Drawing {total} drags (~{est:.0f}s)...")
    sw, _ = cg_screen_size()
    safe_x, safe_y = sw // 2, 50
    start_time = time.time()

    bw = boundary["right_x"] - boundary["left_x"]
    drag_len = max(6, int(bw / cols * 3))

    for i, (col, row) in enumerate(drags):
        x, y = pixel_to_screen(col, row, boundary, cols, rows)
        steps = max(3, drag_len)
        cg_drag(x, y, x + drag_len, y, steps=steps, duration=max(0.06, drag_len * 0.01))
        time.sleep(delay)

        if (i + 1) % 100 == 0:
            cg_move(safe_x, safe_y)
            time.sleep(0.3)
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            remaining = total - (i + 1)
            eta = remaining / rate
            pct = (i + 1) / total * 100
            print(f"  {i + 1}/{total} ({pct:.0f}%) | {elapsed:.0f}s elapsed | ~{eta:.0f}s left")

    cg_move(safe_x, safe_y)
    total_time = time.time() - start_time
    print(f"  Done: {total} drags in {total_time:.0f}s")


# ── Template generator ──

def generate_template(boundary: dict, cols: int = DESIGN_COLS,
                      output_path: str = "template.png"):
    """Generate a blank template PNG matching your card's exact proportions.

    The canvas is a simple rectangle — no cutouts. Paint your design:
      - Black = drawn on card
      - Red   = no-go zone (danger edges near the border)
      - White = skipped background
    """
    rows = compute_rows(boundary, cols)
    img = Image.new("RGB", (cols, rows), (255, 255, 255))
    img.save(output_path)
    print(f"Template saved: {output_path} ({cols}×{rows})")
    print("  Black = draw   Red = no-go   White = skip")
    print("  Tip: add a thin red border around edges if clicking outside kicks you out")


# ── Print helpers ──

def print_usage():
    """Print usage and exit."""
    print("Usage: python draw.py <image.png> [options]")
    print()
    print("Commands:")
    print("  python draw.py logo.png              Draw the image")
    print("  python draw.py --template             Generate blank template")
    print("  python draw.py logo.png --dry-run     Preview without drawing")
    print()
    print("Modes:")
    print("  --mode tiny       Individual pixel drags (precise, consistent)")
    print("  --mode strokes    Row-by-row continuous swipes (faster)")
    print("  --mode test       Draw a big X to verify everything works")
    print()
    print("Options:")
    print("  --dry-run         Show counts without drawing")
    print("  --delay 0.03      Seconds between drags (default: 0.02 strokes, 0.03 tiny)")
    print("  --show-bounds     Move mouse to corners to verify calibration")
    print()
    print(f"Template: {DESIGN_COLS}×N PNG (height auto-computed for your card)")
    print("          Black = draw, Red = no-go, White = skip")
    sys.exit(1)


def print_boundary_info(boundary: dict, image_path: str, cols: int, rows: int, mode: str):
    """Print diagnostic info about the drawing session."""
    bw = boundary["right_x"] - boundary["left_x"]
    bh = boundary["bottom_y"] - boundary["top_y"]
    print(f"Design: {image_path} → {cols}×{rows} grid")
    print(f"Card area: {bw}×{bh} px on screen")
    print(f"Bounds: ({boundary['left_x']},{boundary['top_y']}) → ({boundary['right_x']},{boundary['bottom_y']})")
    print(f"Mode: {mode}")


def show_bounds(boundary: dict):
    """Move mouse to each corner of the drawing area so user can verify calibration."""
    print("\n📐 Moving mouse to drawing area corners for verification...")
    corners = [
        ("Top-left", boundary["left_x"], boundary["top_y"]),
        ("Top-right", boundary["right_x"], boundary["top_y"]),
        ("Bottom-left", boundary["left_x"], boundary["bottom_y"]),
        ("Bottom-right", boundary["right_x"], boundary["bottom_y"]),
    ]
    for name, cx, cy in corners:
        print(f"  {name}: ({cx}, {cy})")
        cg_move(cx, cy)
        time.sleep(0.8)
    print("  Done. Did the mouse land on the card corners?")


def draw_test_x(boundary: dict):
    """Draw a large X across the card as a diagnostic test."""
    wait_for_enter()

    x1, y1 = boundary["left_x"] + 20, boundary["top_y"] + 20
    x2, y2 = boundary["right_x"] - 20, boundary["bottom_y"] - 20
    x3, y3 = boundary["right_x"] - 20, boundary["top_y"] + 20
    x4, y4 = boundary["left_x"] + 20, boundary["bottom_y"] - 20

    for sx, sy, ex, ey in [(x1, y1, x2, y2), (x3, y3, x4, y4)]:
        dist = max(abs(ex - sx), abs(ey - sy))
        steps = max(30, int(dist / 2))
        cg_drag(sx, sy, ex, ey, steps=steps, duration=max(0.3, dist * 0.005))
        time.sleep(0.3)

    print("✅ Test X drawn. Check the card.")


# ── Main ──

def main():
    if len(sys.argv) < 2:
        print_usage()

    # --template flag
    if sys.argv[1] == "--template":
        config = load_config()
        boundary = load_boundary(config)
        generate_template(boundary)
        return

    image_path = sys.argv[1]

    # Parse flags
    dry_run = "--dry-run" in sys.argv
    mode = "strokes"
    delay = None

    for i, arg in enumerate(sys.argv):
        if arg == "--mode" and i + 1 < len(sys.argv):
            mode = sys.argv[i + 1]
        if arg == "--delay" and i + 1 < len(sys.argv):
            delay = float(sys.argv[i + 1])

    if delay is None:
        delay = 0.02 if mode == "strokes" else 0.03

    # Load config and boundary
    config = load_config()
    boundary = load_boundary(config)

    cols = DESIGN_COLS
    rows = compute_rows(boundary, cols)
    print_boundary_info(boundary, image_path, cols, rows, mode)

    # --show-bounds
    if "--show-bounds" in sys.argv:
        show_bounds(boundary)
        return

    # Load design image
    if not Path(image_path).exists():
        print(f"Error: '{image_path}' not found.")
        sys.exit(1)
    draw_mask, no_go_mask = load_image(image_path, cols, rows)
    drawable = int(np.sum(draw_mask))
    no_go_count = int(np.sum(no_go_mask))
    print(f"Drawable pixels: {drawable}  (red no-go: {no_go_count})")

    # --mode test
    if mode == "test":
        draw_test_x(boundary)
        return

    # Extract drawing instructions
    if mode == "strokes":
        strokes = extract_strokes(draw_mask, no_go_mask, cols, rows)
        print(f"Strokes: {len(strokes)}")
        if dry_run:
            print("🔍 DRY RUN — no drawing performed")
            return
        wait_for_enter()
        draw_strokes(strokes, boundary, cols, rows, delay=delay)

    else:  # tiny (default fallback)
        drags = extract_tiny_drags(draw_mask, no_go_mask, cols, rows)
        est = f"~{len(drags) * delay:.0f}s"
        print(f"Tiny drags: {len(drags)} ({est})")
        if dry_run:
            print("🔍 DRY RUN — no drawing performed")
            return
        wait_for_enter()
        draw_tiny_drags(drags, boundary, cols, rows, delay=delay)

    print("\n✅ Done! Check your phone — the design should be drawn.")


if __name__ == "__main__":
    main()
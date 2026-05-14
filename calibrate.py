#!/usr/bin/env python3
"""
CashDraw iOS — Draw custom designs on your Cash App card via iPhone Mirroring.

Click the four corners of the drawing area. Simple, accurate, one-time setup.

Usage:
    python calibrate.py --manual
"""

import sys
import json
import pyautogui

pyautogui.FAILSAFE = False


def click_corners() -> dict:
    """Have user click the four corners of the drawing area."""
    corners = [
        ("top-left corner of the drawing area", "left_x", "top_y"),
        ("top-right corner of the drawing area", "right_x", "top_y"),
        ("bottom-left corner of the drawing area", "left_x", "bottom_y"),
        ("bottom-right corner of the drawing area", "right_x", "bottom_y"),
    ]

    coords = {}

    print("\n📐 Click the four corners of the drawing area on your Cash App card.\n")
    print("Before starting:")
    print("  - Open Cash App → Card → Design Card → Draw")
    print("  - Make sure iPhone Mirroring is visible (not behind other windows)\n")

    for i, (description, x_key, y_key) in enumerate(corners):
        input(f"Step {i + 1}/4: Move mouse to the {description} and press Enter...")
        x, y = pyautogui.position()
        coords[x_key] = int(x)
        coords[y_key] = int(y)
        print(f"  → ({x}, {y})")

    return coords


def main():
    if len(sys.argv) < 2 or sys.argv[1] != "--manual":
        print("Usage: python calibrate.py --manual")
        print()
        print("Click the four corners of the Cash App card's drawing area.")
        print("One-time setup — saves config.json for use with draw.py.")
        sys.exit(1)

    print("=" * 50)
    print("  CashDraw iOS — Manual Calibration")
    print("=" * 50)

    boundary = click_corners()

    bw = boundary["right_x"] - boundary["left_x"]
    bh = boundary["bottom_y"] - boundary["top_y"]

    print(f"\nDrawing area: {bw}×{bh} px")
    print(f"  Top-left:     ({boundary['left_x']}, {boundary['top_y']})")
    print(f"  Bottom-right: ({boundary['right_x']}, {boundary['bottom_y']})")

    config = {
        "boundary": boundary,
    }

    with open("config.json", "w") as f:
        json.dump(config, f, indent=2)

    print(f"\n✅ config.json saved")
    print(f"   Next:  python draw.py --template")
    print(f"          python draw.py template.png --mode test")
    print(f"          python draw.py template.png --mode tiny")


if __name__ == "__main__":
    main()
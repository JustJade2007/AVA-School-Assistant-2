"""
Visual Grounding and Set-of-Marks (SoM) Engine for AVA School Assistant 2.
Enhances screen screenshots with:
1. Marginal coordinate rulers (0..1000 normalized axes along top and left borders)
2. Numbered anchor badges ([1], [2], [3]...) over candidate interactive controls
   (radio buttons, checkboxes, input boxes, action buttons)

Operates with ZERO additional AI token consumption because multimodal vision models
charge a flat token rate based strictly on raw image input dimensions.
"""

import math
import logging
from typing import Dict, Any, List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter

logger = logging.getLogger("visual_grounding")


def draw_coordinate_ruler(image: Image.Image) -> Image.Image:
    """
    Renders fine, high-contrast normalized coordinate axes (0..1000) along the top and left
    margins of the image.

    Top Ruler (Horizontal X axis, 0 -> 1000):
    - Major ticks and numbers every 100 normalized units (100, 200, ... 900)
    - Medium ticks every 50 normalized units
    - Minor ticks every 10 normalized units

    Left Ruler (Vertical Y axis, 0 -> 1000):
    - Major ticks and numbers every 100 normalized units
    - Medium ticks every 50 normalized units
    - Minor ticks every 10 normalized units

    Dual-color contrasting strokes ensure visibility on both dark and light web pages.
    """
    grounded = image.copy().convert("RGB")
    draw = ImageDraw.Draw(grounded, "RGBA")
    w, h = grounded.size

    if w < 100 or h < 100:
        return grounded

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    # Colors
    bg_bar = (15, 23, 42, 210)       # Dark slate semi-transparent strip
    tick_major = (0, 255, 204, 255)   # Vibrant cyan
    tick_minor = (148, 163, 184, 180) # Subtle slate
    tick_shadow = (0, 0, 0, 230)      # Contrast drop shadow
    text_color = (255, 255, 255, 255)

    ruler_h = 16
    ruler_w = 26

    # 1. Background margin strips for extreme legibility
    draw.rectangle([0, 0, w, ruler_h], fill=bg_bar)
    draw.rectangle([0, 0, ruler_w, h], fill=bg_bar)

    # Corner box
    draw.rectangle([0, 0, ruler_w, ruler_h], fill=(30, 41, 59, 255))
    if font:
        draw.text((2, 2), "XY", fill=tick_major, font=font)

    # 2. Top X-Axis Ruler (0 .. 1000)
    for n in range(10, 1000, 10):
        px = int(n * w / 1000.0)
        is_major = (n % 100 == 0)
        is_mid = (n % 50 == 0 and not is_major)

        if is_major:
            draw.line([(px, 0), (px, ruler_h - 1)], fill=tick_shadow, width=2)
            draw.line([(px, 0), (px, ruler_h - 2)], fill=tick_major, width=1)
            lbl = str(n)
            if px + 22 < w:
                draw.text((px + 2, 2), lbl, fill=text_color, font=font)
        elif is_mid:
            draw.line([(px, ruler_h - 7), (px, ruler_h - 1)], fill=tick_shadow, width=2)
            draw.line([(px, ruler_h - 6), (px, ruler_h - 2)], fill=tick_major, width=1)
        else:
            draw.line([(px, ruler_h - 4), (px, ruler_h - 1)], fill=tick_minor, width=1)

    # 3. Left Y-Axis Ruler (0 .. 1000)
    for n in range(10, 1000, 10):
        py = int(n * h / 1000.0)
        is_major = (n % 100 == 0)
        is_mid = (n % 50 == 0 and not is_major)

        if is_major:
            draw.line([(0, py), (ruler_w - 1, py)], fill=tick_shadow, width=2)
            draw.line([(0, py), (ruler_w - 2, py)], fill=tick_major, width=1)
            lbl = str(n)
            if py + 10 < h:
                draw.text((2, py + 2), lbl, fill=text_color, font=font)
        elif is_mid:
            draw.line([(ruler_w - 7, py), (ruler_w - 1, py)], fill=tick_shadow, width=2)
            draw.line([(ruler_w - 6, py), (ruler_w - 2, py)], fill=tick_major, width=1)
        else:
            draw.line([(ruler_w - 4, py), (ruler_w - 1, py)], fill=tick_minor, width=1)

    return grounded


def detect_candidate_control_anchors(
    image: Image.Image,
    region: Tuple[int, int, int, int],
    prior_actions: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Scans the image using edge detection and shape heuristics to discover candidate
    interactive elements (radio buttons, checkboxes, input boxes, buttons).
    Returns a list of deduplicated anchors sorted in natural reading order (top-to-bottom, left-to-right).
    """
    w, h = image.size
    ox, oy, rw, rh = region
    scale_x = rw / float(w)
    scale_y = rh / float(h)

    anchors: List[Dict[str, Any]] = []

    # Include prior known action coordinates or sibling choice coordinates as high-priority anchors
    if prior_actions:
        for act in prior_actions:
            sx = act.get("screen_x", act.get("x"))
            sy = act.get("screen_y", act.get("y"))
            if sx is not None and sy is not None:
                isx, isy = int(sx), int(sy)
                lx = int((isx - ox) / scale_x)
                ly = int((isy - oy) / scale_y)
                if 0 <= lx < w and 0 <= ly < h:
                    anchors.append({
                        "type": act.get("type", "known_target"),
                        "img_x": lx,
                        "img_y": ly,
                        "screen_x": isx,
                        "screen_y": isy,
                        "confidence": 1.0
                    })

    try:
        gray = image.convert("L")
        edges = gray.filter(ImageFilter.FIND_EDGES)
        ep = edges.load()

        step_y = max(4, h // 200)
        step_x = max(4, w // 260)

        # Ignore extreme top and left ruler margin bands during detection
        min_x, max_x = 30, w - 20
        min_y, max_y = 22, h - 20

        for cy in range(min_y, max_y, step_y):
            for cx in range(min_x, max_x, step_x):
                # Test circle perimeter (radii 8..10)
                for r in [8, 9, 10]:
                    if cx - r < 2 or cx + r >= w - 2 or cy - r < 2 or cy + r >= h - 2:
                        continue
                    pts = [
                        ep[cx + r, cy], ep[cx - r, cy],
                        ep[cx, cy + r], ep[cx, cy - r],
                        ep[int(cx + r * 0.7), int(cy + r * 0.7)],
                        ep[int(cx - r * 0.7), int(cy + r * 0.7)],
                        ep[int(cx + r * 0.7), int(cy - r * 0.7)],
                        ep[int(cx - r * 0.7), int(cy - r * 0.7)]
                    ]
                    hits = sum(1 for p in pts if p >= 28)
                    if hits >= 6:
                        anchors.append({
                            "type": "choice_control",
                            "img_x": cx,
                            "img_y": cy,
                            "screen_x": int(ox + cx * scale_x),
                            "screen_y": int(oy + cy * scale_y),
                            "confidence": hits / 8.0
                        })
                        break

    except Exception as e:
        logger.debug(f"Anchor detection error: {e}")

    # Deduplicate anchors that are closer than 20px to each other
    deduped: List[Dict[str, Any]] = []
    for cand in anchors:
        is_dup = False
        for existing in deduped:
            dist = math.hypot(cand["img_x"] - existing["img_x"], cand["img_y"] - existing["img_y"])
            if dist < 20:
                is_dup = True
                if cand.get("confidence", 0) > existing.get("confidence", 0):
                    existing.update(cand)
                break
        if not is_dup:
            deduped.append(cand)

    # Sort top-to-bottom, left-to-right (natural reading order)
    def _sort_key(a: Dict[str, Any]):
        row_bucket = a["img_y"] // 16
        return (row_bucket, a["img_x"])

    deduped.sort(key=_sort_key)
    return deduped[:48]


def overlay_set_of_marks(
    image: Image.Image,
    anchors: List[Dict[str, Any]]
) -> Tuple[Image.Image, Dict[int, Dict[str, Any]]]:
    """
    Overlays vibrant numbered badge tags [1], [2], [3]... directly onto the image
    over candidate interactive elements.
    Returns:
        (marked_image, mark_registry)
    where mark_registry maps mark_id -> {screen_x, screen_y, norm_x, norm_y, bounds, type}
    """
    marked = image.copy().convert("RGB")
    draw = ImageDraw.Draw(marked, "RGBA")
    w, h = marked.size

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    registry: Dict[int, Dict[str, Any]] = {}

    badge_bg = (6, 182, 212, 240)    # Vibrant cyan #06b6d4
    badge_border = (0, 0, 0, 255)     # High-contrast black outline
    text_color = (0, 0, 0, 255)       # Solid black text

    for idx, anchor in enumerate(anchors, start=1):
        mark_id = idx
        ix = anchor["img_x"]
        iy = anchor["img_y"]
        sx = anchor["screen_x"]
        sy = anchor["screen_y"]
        norm_x = int(round(ix * 1000.0 / w))
        norm_y = int(round(iy * 1000.0 / h))

        lbl = str(mark_id)
        text_w = len(lbl) * 6 + 4
        badge_w = max(16, text_w + 6)
        badge_h = 13

        bx1 = max(2, ix - badge_w // 2)
        by1 = max(2, iy - badge_h // 2)
        bx2 = min(w - 2, bx1 + badge_w)
        by2 = min(h - 2, by1 + badge_h)

        # Draw badge pill
        draw.rounded_rectangle([bx1 - 1, by1 - 1, bx2 + 1, by2 + 1], radius=3, fill=badge_border)
        draw.rounded_rectangle([bx1, by1, bx2, by2], radius=3, fill=badge_bg)

        # Center number text in badge
        tx = bx1 + (badge_w - (len(lbl) * 6)) // 2
        ty = by1 + 1
        if font:
            draw.text((tx, ty), lbl, fill=text_color, font=font)

        registry[mark_id] = {
            "mark_id": mark_id,
            "screen_x": sx,
            "screen_y": sy,
            "img_x": ix,
            "img_y": iy,
            "norm_x": norm_x,
            "norm_y": norm_y,
            "type": anchor.get("type", "control"),
            "bounds": (bx1, by1, bx2, by2)
        }

    return marked, registry


def prepare_grounded_image(
    image: Image.Image,
    region: Tuple[int, int, int, int],
    prior_actions: Optional[List[Dict[str, Any]]] = None,
    enable_marks: bool = True,
    enable_rulers: bool = True
) -> Tuple[Image.Image, Dict[int, Dict[str, Any]]]:
    """
    Prepares a fully grounded screenshot for AI vision consumption.
    1. Discovers interactive candidate controls and overlays numbered Set-of-Marks tags.
    2. Draws normalized 0..1000 coordinate rulers along the margins.
    Returns:
        (grounded_image, mark_registry)
    """
    grounded = image
    registry: Dict[int, Dict[str, Any]] = {}

    if enable_marks:
        anchors = detect_candidate_control_anchors(image, region=region, prior_actions=prior_actions)
        if anchors:
            grounded, registry = overlay_set_of_marks(grounded, anchors)

    if enable_rulers:
        grounded = draw_coordinate_ruler(grounded)

    return grounded, registry

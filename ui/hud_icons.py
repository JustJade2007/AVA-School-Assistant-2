"""
High-DPI Vector Icon Generator for AVA School Assistant 2 HUD Overlay.
Renders razor-sharp anti-aliased geometric icons via supersampled PIL canvas
and converts them to CTkImage objects for crisp rendering on any DPI scale.
"""

from typing import Dict, Tuple, Union
from PIL import Image, ImageDraw
import customtkinter as ctk
import os
import math
from ui.asset_loader import get_asset_path


_ICON_CACHE: Dict[Tuple[str, Tuple[int, int], str], ctk.CTkImage] = {}

# Mapping from canonical HUD icon keys to dedicated PNG assets in ui/images/icons/
_IMAGE_ICON_MAP = {
    "close": "icons8-close-48.png",
    "minimize": "icons8-minimize-48.png",
    "settings": "icons8-settings-48.png",
    "debug": "icons8-console-48.png",
    "console": "icons8-console-48.png",
    "snip": "icons8-snip-48.png",
    "playground": "playground.png",
    "solve": "icons8-solve-48.png",
    "execute": "icons8-confirm-48.png",
    "confirm": "icons8-confirm-48.png",
    "next": "icons8-next-48.png",
    "stop": "icons8-stop-48.png",
    "pause": "icons8-pause-48.png",
    "resume": "icons8-resume-button-48.png",
    "retry": "icons8-resume-button-48.png",
}


def get_hud_icon(name: str, size: Union[int, Tuple[int, int]] = 16, color: str = "#ffffff") -> ctk.CTkImage:
    """
    Returns a cached or freshly generated high-DPI CTkImage icon.
    First checks ui/images/icons/ for dedicated high-fidelity PNG assets.
    If not available, falls back to procedurally drawn 4x supersampled vector shapes.
    Supports size as int or (width, height) tuple.
    """
    if isinstance(size, (tuple, list)):
        w_px, h_px = int(size[0]), int(size[1])
    else:
        w_px = h_px = int(size)

    cache_key = (name, (w_px, h_px), color)
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]

    # 1. Attempt loading from ui/images/icons/
    if name in _IMAGE_ICON_MAP:
        asset_rel = os.path.join("icons", _IMAGE_ICON_MAP[name])
        asset_path = get_asset_path(asset_rel)
        if asset_path and os.path.exists(asset_path):
            try:
                raw_img = Image.open(asset_path).convert("RGBA")
                resized_img = raw_img.resize((w_px, h_px), Image.Resampling.LANCZOS)
                ctk_icon = ctk.CTkImage(light_image=resized_img, dark_image=resized_img, size=(w_px, h_px))
                _ICON_CACHE[cache_key] = ctk_icon
                return ctk_icon
            except Exception:
                pass

    # 2. Fallback: Procedural supersampled vector drawing
    dim = max(w_px, h_px)
    scale = 4
    canvas_size = dim * scale
    img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = 3 * scale
    c = canvas_size / 2.0
    r = (canvas_size - 2 * pad) / 2.0

    if name == "close":
        # Crisp 'X'
        w = max(2, int(1.8 * scale))
        draw.line([pad, pad, canvas_size - pad, canvas_size - pad], fill=color, width=w)
        draw.line([pad, canvas_size - pad, canvas_size - pad, pad], fill=color, width=w)

    elif name == "minimize":
        # Clean horizontal bar
        w = max(2, int(2.0 * scale))
        y = c + 1 * scale
        draw.line([pad + 2 * scale, y, canvas_size - pad - 2 * scale, y], fill=color, width=w)

    elif name in ["collapse_up", "collapse"]:
        # Upward chevron
        w = max(2, int(2.0 * scale))
        draw.line([pad + 2 * scale, c + 3 * scale, c, c - 3 * scale], fill=color, width=w)
        draw.line([c, c - 3 * scale, canvas_size - pad - 2 * scale, c + 3 * scale], fill=color, width=w)

    elif name == "collapse_down":
        # Downward chevron
        w = max(2, int(2.0 * scale))
        draw.line([pad + 2 * scale, c - 3 * scale, c, c + 3 * scale], fill=color, width=w)
        draw.line([c, c + 3 * scale, canvas_size - pad - 2 * scale, c - 3 * scale], fill=color, width=w)

    elif name == "settings":
        # Modern 6-tooth gear
        teeth = 6
        inner_r = r * 0.45
        outer_r = r * 0.85
        tooth_r = r * 1.05
        points = []
        for i in range(teeth * 2):
            angle = i * (math.pi / teeth)
            curr_r = tooth_r if (i % 2 == 0) else outer_r
            x1 = c + curr_r * math.cos(angle - 0.15)
            y1 = c + curr_r * math.sin(angle - 0.15)
            x2 = c + curr_r * math.cos(angle + 0.15)
            y2 = c + curr_r * math.sin(angle + 0.15)
            points.extend([(x1, y1), (x2, y2)])
        if points:
            draw.polygon(points, fill=color)
            # Center hole cutout
            draw.ellipse([c - inner_r, c - inner_r, c + inner_r, c + inner_r], fill=(0, 0, 0, 0))

    elif name == "debug":
        # Sleek bug icon
        body_r = r * 0.6
        draw.ellipse([c - body_r, c - body_r * 0.8, c + body_r, c + body_r * 1.1], fill=color)
        head_r = body_r * 0.55
        draw.ellipse([c - head_r, c - body_r * 1.3, c + head_r, c - body_r * 0.4], fill=color)
        # Antennae & legs
        lw = max(1, int(1.4 * scale))
        draw.line([c - 2 * scale, c - body_r * 1.2, c - 5 * scale, c - body_r * 1.6], fill=color, width=lw)
        draw.line([c + 2 * scale, c - body_r * 1.2, c + 5 * scale, c - body_r * 1.6], fill=color, width=lw)
        # Legs
        draw.line([c - body_r * 0.7, c, c - body_r * 1.4, c - 2 * scale], fill=color, width=lw)
        draw.line([c + body_r * 0.7, c, c + body_r * 1.4, c - 2 * scale], fill=color, width=lw)
        draw.line([c - body_r * 0.7, c + 4 * scale, c - body_r * 1.4, c + 6 * scale], fill=color, width=lw)
        draw.line([c + body_r * 0.7, c + 4 * scale, c + body_r * 1.4, c + 6 * scale], fill=color, width=lw)

    elif name == "snip":
        # Crosshairs / Snip viewfinder icon
        lw = max(2, int(1.8 * scale))
        gap = 3 * scale
        # Top-left corner
        draw.line([pad, pad + 5 * scale, pad, pad], fill=color, width=lw)
        draw.line([pad, pad, pad + 5 * scale, pad], fill=color, width=lw)
        # Top-right corner
        draw.line([canvas_size - pad - 5 * scale, pad, canvas_size - pad, pad], fill=color, width=lw)
        draw.line([canvas_size - pad, pad, canvas_size - pad, pad + 5 * scale], fill=color, width=lw)
        # Bottom-left corner
        draw.line([pad, canvas_size - pad - 5 * scale, pad, canvas_size - pad], fill=color, width=lw)
        draw.line([pad, canvas_size - pad, pad + 5 * scale, canvas_size - pad], fill=color, width=lw)
        # Bottom-right corner
        draw.line([canvas_size - pad - 5 * scale, canvas_size - pad, canvas_size - pad, canvas_size - pad], fill=color, width=lw)
        draw.line([canvas_size - pad, canvas_size - pad - 5 * scale, canvas_size - pad, canvas_size - pad], fill=color, width=lw)
        # Center target dot
        draw.ellipse([c - 1.5 * scale, c - 1.5 * scale, c + 1.5 * scale, c + 1.5 * scale], fill=color)

    elif name in ["target", "crosshair"]:
        # Bullseye target with crosshairs (used for planned-click visualizer toggle)
        lw = max(1, int(1.4 * scale))
        outer_r = r * 0.85
        inner_r = r * 0.45
        draw.ellipse([c - outer_r, c - outer_r, c + outer_r, c + outer_r], outline=color, width=lw)
        draw.ellipse([c - inner_r, c - inner_r, c + inner_r, c + inner_r], outline=color, width=lw)
        draw.ellipse([c - 1.8 * scale, c - 1.8 * scale, c + 1.8 * scale, c + 1.8 * scale], fill=color)
        # Crosshairs extending outward
        draw.line([c, pad, c, c - inner_r * 0.6], fill=color, width=lw)
        draw.line([c, c + inner_r * 0.6, c, canvas_size - pad], fill=color, width=lw)
        draw.line([pad, c, c - inner_r * 0.6, c], fill=color, width=lw)
        draw.line([c + inner_r * 0.6, c, canvas_size - pad, c], fill=color, width=lw)

    elif name == "playground":
        # Document & quill pen icon
        w = max(2, int(1.8 * scale))
        x0, y0 = pad + 1 * scale, pad + 1 * scale
        x1, y1 = canvas_size - pad - 3 * scale, canvas_size - pad
        draw.rounded_rectangle([x0, y0, x1, y1], radius=2 * scale, outline=color, width=w)
        # Content lines
        draw.line([x0 + 3 * scale, y0 + 4 * scale, x1 - 3 * scale, y0 + 4 * scale], fill=color, width=max(1, int(1.2 * scale)))
        draw.line([x0 + 3 * scale, y0 + 7 * scale, x1 - 5 * scale, y0 + 7 * scale], fill=color, width=max(1, int(1.2 * scale)))
        draw.line([x0 + 3 * scale, y0 + 10 * scale, x1 - 4 * scale, y0 + 10 * scale], fill=color, width=max(1, int(1.2 * scale)))

    elif name == "solve":
        # Solid right play triangle
        p1 = (c - r * 0.55, c - r * 0.8)
        p2 = (c - r * 0.55, c + r * 0.8)
        p3 = (c + r * 0.85, c)
        draw.polygon([p1, p2, p3], fill=color)

    elif name == "execute":
        # Dynamic lightning bolt
        pts = [
            (c + 1 * scale, pad),
            (c - 4 * scale, c + 1 * scale),
            (c - 1 * scale, c + 1 * scale),
            (c - 2 * scale, canvas_size - pad),
            (c + 4 * scale, c - 1 * scale),
            (c + 1 * scale, c - 1 * scale),
        ]
        draw.polygon(pts, fill=color)

    elif name == "stop":
        # Solid rounded stop square
        sq_r = r * 0.72
        draw.rounded_rectangle(
            [c - sq_r, c - sq_r, c + sq_r, c + sq_r],
            radius=int(2.5 * scale),
            fill=color
        )

    elif name == "next":
        # Double right chevrons
        w = max(2, int(2.0 * scale))
        offset = 3.5 * scale
        # Chevron 1
        draw.line([c - offset - 2 * scale, c - r * 0.6, c - offset + 2 * scale, c], fill=color, width=w)
        draw.line([c - offset + 2 * scale, c, c - offset - 2 * scale, c + r * 0.6], fill=color, width=w)
        # Chevron 2
        draw.line([c + offset - 2 * scale, c - r * 0.6, c + offset + 2 * scale, c], fill=color, width=w)
        draw.line([c + offset + 2 * scale, c, c + offset - 2 * scale, c + r * 0.6], fill=color, width=w)

    elif name == "pause":
        # Double vertical rounded pause bars
        bar_w = 2.5 * scale
        gap = 2.5 * scale
        bar_h = r * 0.8
        draw.rounded_rectangle([c - gap - bar_w, c - bar_h, c - gap, c + bar_h], radius=int(1.2 * scale), fill=color)
        draw.rounded_rectangle([c + gap, c - bar_h, c + gap + bar_w, c + bar_h], radius=int(1.2 * scale), fill=color)

    elif name == "cloak":
        # Shield icon
        w = max(2, int(1.8 * scale))
        pts = [
            (c, pad),
            (canvas_size - pad, pad + 2 * scale),
            (canvas_size - pad, c + 2 * scale),
            (c, canvas_size - pad),
            (pad, c + 2 * scale),
            (pad, pad + 2 * scale),
        ]
        draw.polygon(pts, outline=color, fill=None)
        # Inner checkmark
        draw.line([c - 3 * scale, c, c - 1 * scale, c + 3 * scale], fill=color, width=w)
        draw.line([c - 1 * scale, c + 3 * scale, c + 4 * scale, c - 2 * scale], fill=color, width=w)

    elif name == "retry":
        # Circular refresh arrow
        w = max(2, int(1.8 * scale))
        draw.arc([c - r * 0.8, c - r * 0.8, c + r * 0.8, c + r * 0.8], start=30, end=300, fill=color, width=w)
        # Arrowhead at start
        tip_x = c + r * 0.8 * math.cos(math.radians(30))
        tip_y = c + r * 0.8 * math.sin(math.radians(30))
        draw.polygon([
            (tip_x, tip_y),
            (tip_x + 3 * scale, tip_y - 4 * scale),
            (tip_x - 3 * scale, tip_y - 4 * scale)
        ], fill=color)

    else:
        # Generic circle
        draw.ellipse([pad, pad, canvas_size - pad, canvas_size - pad], fill=color)

    # Downscale smoothly using Lanczos
    final_img = img.resize((w_px, h_px), Image.Resampling.LANCZOS)
    ctk_icon = ctk.CTkImage(light_image=final_img, dark_image=final_img, size=(w_px, h_px))
    _ICON_CACHE[cache_key] = ctk_icon
    return ctk_icon

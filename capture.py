"""
FRANZ capture -- GDI screen capture + magenta visual annotations + PNG + base64

Standalone subprocess. Reads JSON from stdin, writes base64 PNG to stdout.

Input (stdin JSON):
    actions     list[str]   Action lines to annotate (may be empty)
    width       int         Target image width
    height      int         Target image height
    marks       bool        Whether to draw visual annotations

Output (stdout):
    Raw base64-encoded PNG string
"""
import base64
import ctypes
import ctypes.wintypes
import json
import math
import struct
import sys
import zlib
from typing import Final

type Color = tuple[int, int, int, int]

ACTION_PRIMARY: Final[Color] = (255, 50, 200, 255)
ACTION_SECONDARY: Final[Color] = (255, 180, 240, 255)
ACTION_OUTLINE: Final[Color] = (40, 0, 30, 200)

_BI_RGB: Final[int] = 0
_DIB_RGB: Final[int] = 0
_SRCCOPY: Final[int] = 0x00CC0020
_CAPTUREBLT: Final[int] = 0x40000000
_HALFTONE: Final[int] = 4


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.wintypes.DWORD),
        ("biWidth", ctypes.wintypes.LONG),
        ("biHeight", ctypes.wintypes.LONG),
        ("biPlanes", ctypes.wintypes.WORD),
        ("biBitCount", ctypes.wintypes.WORD),
        ("biCompression", ctypes.wintypes.DWORD),
        ("biSizeImage", ctypes.wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.wintypes.LONG),
        ("biYPelsPerMeter", ctypes.wintypes.LONG),
        ("biClrUsed", ctypes.wintypes.DWORD),
        ("biClrImportant", ctypes.wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BITMAPINFOHEADER),
        ("bmiColors", ctypes.wintypes.DWORD * 3),
    ]


_shcore: Final[ctypes.WinDLL] = ctypes.WinDLL("shcore", use_last_error=True)
_shcore.SetProcessDpiAwareness(2)
_user32: Final[ctypes.WinDLL] = ctypes.WinDLL("user32", use_last_error=True)
_gdi32: Final[ctypes.WinDLL] = ctypes.WinDLL("gdi32", use_last_error=True)
_screen_w: Final[int] = _user32.GetSystemMetrics(0)
_screen_h: Final[int] = _user32.GetSystemMetrics(1)


def _make_bmi(w: int, h: int) -> _BITMAPINFO:
    bmi = _BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = _BI_RGB
    return bmi


def _capture_bgra(sw: int, sh: int) -> bytes:
    sdc = _user32.GetDC(0)
    memdc = _gdi32.CreateCompatibleDC(sdc)
    bits = ctypes.c_void_p()
    hbmp = _gdi32.CreateDIBSection(sdc, ctypes.byref(_make_bmi(sw, sh)), _DIB_RGB, ctypes.byref(bits), None, 0)
    old = _gdi32.SelectObject(memdc, hbmp)
    _gdi32.BitBlt(memdc, 0, 0, sw, sh, sdc, 0, 0, _SRCCOPY | _CAPTUREBLT)
    raw = bytes((ctypes.c_ubyte * (sw * sh * 4)).from_address(bits.value))
    _gdi32.SelectObject(memdc, old)
    _gdi32.DeleteObject(hbmp)
    _gdi32.DeleteDC(memdc)
    _user32.ReleaseDC(0, sdc)
    return raw


def _downsample_bgra(src: bytes, sw: int, sh: int, dw: int, dh: int) -> bytes:
    sdc = _user32.GetDC(0)
    src_dc = _gdi32.CreateCompatibleDC(sdc)
    dst_dc = _gdi32.CreateCompatibleDC(sdc)
    src_bmp = _gdi32.CreateCompatibleBitmap(sdc, sw, sh)
    old_src = _gdi32.SelectObject(src_dc, src_bmp)
    _gdi32.SetDIBits(sdc, src_bmp, 0, sh, src, ctypes.byref(_make_bmi(sw, sh)), _DIB_RGB)
    dst_bits = ctypes.c_void_p()
    dst_bmp = _gdi32.CreateDIBSection(sdc, ctypes.byref(_make_bmi(dw, dh)), _DIB_RGB, ctypes.byref(dst_bits), None, 0)
    old_dst = _gdi32.SelectObject(dst_dc, dst_bmp)
    _gdi32.SetStretchBltMode(dst_dc, _HALFTONE)
    _gdi32.SetBrushOrgEx(dst_dc, 0, 0, None)
    _gdi32.StretchBlt(dst_dc, 0, 0, dw, dh, src_dc, 0, 0, sw, sh, _SRCCOPY)
    raw = bytearray((ctypes.c_ubyte * (dw * dh * 4)).from_address(dst_bits.value))
    raw[3::4] = b"\xff" * (dw * dh)
    out = bytes(raw)
    _gdi32.SelectObject(dst_dc, old_dst)
    _gdi32.SelectObject(src_dc, old_src)
    _gdi32.DeleteObject(dst_bmp)
    _gdi32.DeleteObject(src_bmp)
    _gdi32.DeleteDC(dst_dc)
    _gdi32.DeleteDC(src_dc)
    _user32.ReleaseDC(0, sdc)
    return out


def _bgra_to_rgba(bgra: bytes) -> bytes:
    n = len(bgra)
    out = bytearray(n)
    out[0::4] = bgra[2::4]
    out[1::4] = bgra[1::4]
    out[2::4] = bgra[0::4]
    out[3::4] = b"\xff" * (n // 4)
    return bytes(out)


def _encode_png(rgba: bytes, w: int, h: int) -> bytes:
    stride = w * 4
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw.extend(rgba[y * stride : (y + 1) * stride])
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 6)

    def _chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def _set_pixel(data: bytearray, w: int, h: int, x: int, y: int, c: Color) -> None:
    if 0 <= x < w and 0 <= y < h:
        i = (y * w + x) << 2
        data[i] = c[0]
        data[i + 1] = c[1]
        data[i + 2] = c[2]
        data[i + 3] = c[3]


def _set_pixel_thick(data: bytearray, w: int, h: int, x: int, y: int, c: Color, t: int = 1) -> None:
    half = t >> 1
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            _set_pixel(data, w, h, x + dx, y + dy, c)


def _draw_line(d: bytearray, w: int, h: int, x1: int, y1: int, x2: int, y2: int, c: Color, t: int = 3) -> None:
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    err = dx - dy
    x, y = x1, y1
    while True:
        _set_pixel_thick(d, w, h, x, y, c, t)
        if x == x2 and y == y2:
            break
        e2 = err << 1
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


def _draw_dashed_line(d: bytearray, w: int, h: int, x1: int, y1: int, x2: int, y2: int, c: Color, t: int = 2, dash: int = 8, gap: int = 5) -> None:
    dx, dy = x2 - x1, y2 - y1
    dist = max(1, int(math.hypot(dx, dy)))
    cycle = dash + gap
    for i in range(dist + 1):
        if (i % cycle) < dash:
            frac = i / dist
            _set_pixel_thick(d, w, h, int(x1 + dx * frac), int(y1 + dy * frac), c, t)


def _draw_circle(d: bytearray, w: int, h: int, cx: int, cy: int, r: int, c: Color, filled: bool = False) -> None:
    r2 = r * r
    inner2 = (r - 2) ** 2
    for oy in range(-r, r + 1):
        for ox in range(-r, r + 1):
            dist2 = ox * ox + oy * oy
            if filled:
                if dist2 <= r2:
                    _set_pixel(d, w, h, cx + ox, cy + oy, c)
            elif inner2 <= dist2 <= r2:
                _set_pixel(d, w, h, cx + ox, cy + oy, c)


def _fill_triangle(d: bytearray, w: int, h: int, x1: int, y1: int, x2: int, y2: int, x3: int, y3: int, c: Color) -> None:
    lo_x = max(0, min(x1, x2, x3))
    hi_x = min(w - 1, max(x1, x2, x3))
    lo_y = max(0, min(y1, y2, y3))
    hi_y = min(h - 1, max(y1, y2, y3))

    def _edge(px: int, py: int, ax: int, ay: int, bx: int, by: int) -> int:
        return (px - bx) * (ay - by) - (ax - bx) * (py - by)

    for py in range(lo_y, hi_y + 1):
        for px in range(lo_x, hi_x + 1):
            d1 = _edge(px, py, x1, y1, x2, y2)
            d2 = _edge(px, py, x2, y2, x3, y3)
            d3 = _edge(px, py, x3, y3, x1, y1)
            if not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0)):
                _set_pixel(d, w, h, px, py, c)


def _draw_arrowhead(d: bytearray, w: int, h: int, x1: int, y1: int, x2: int, y2: int, c: Color, t: int = 3, length: int = 15, angle_deg: float = 30.0) -> None:
    angle = math.atan2(y2 - y1, x2 - x1)
    ha = math.radians(angle_deg)
    lx = int(x2 - length * math.cos(angle - ha))
    ly = int(y2 - length * math.sin(angle - ha))
    rx = int(x2 - length * math.cos(angle + ha))
    ry = int(y2 - length * math.sin(angle + ha))
    _draw_line(d, w, h, x2, y2, lx, ly, c, t)
    _draw_line(d, w, h, x2, y2, rx, ry, c, t)
    _fill_triangle(d, w, h, x2, y2, lx, ly, rx, ry, c)


def _draw_dashed_arrow(d: bytearray, w: int, h: int, x1: int, y1: int, x2: int, y2: int, c: Color, t: int = 2, dash: int = 8, gap: int = 5, head_len: int = 15, head_deg: float = 30.0) -> None:
    _draw_dashed_line(d, w, h, x1, y1, x2, y2, c, t, dash, gap)
    _draw_arrowhead(d, w, h, x1, y1, x2, y2, c, max(t, 3), head_len, head_deg)


_GLYPH_CURSOR: Final[list[str]] = [
    "#           ",
    "##          ",
    "#.#         ",
    "#..#        ",
    "#...#       ",
    "#....#      ",
    "#.....#     ",
    "#......#    ",
    "#.......#   ",
    "#........#  ",
    "#.....#####",
    "#..#..#     ",
    "#.# #..#    ",
    "##  #..#    ",
    "#    #..#   ",
    "     ###    ",
]

_GLYPH_CURSOR_RIGHT: Final[list[str]] = [
    "#           ",
    "##          ",
    "#.#         ",
    "#..#        ",
    "#...#       ",
    "#....#      ",
    "#.....#     ",
    "#......#    ",
    "#.......#   ",
    "#........#  ",
    "#.....#####",
    "#..#..# ##  ",
    "#.# #..##.# ",
    "##  #..### ",
    "#    #..#   ",
    "     ###    ",
]

_GLYPH_IBEAM: Final[list[str]] = [
    " ### ",
    "  #  ",
    "  #  ",
    "  #  ",
    "  #  ",
    "  #  ",
    "  #  ",
    "  #  ",
    "  #  ",
    "  #  ",
    "  #  ",
    "  #  ",
    "  #  ",
    " ### ",
]

_IBEAM_W: Final[int] = len(_GLYPH_IBEAM[0])
_IBEAM_H: Final[int] = len(_GLYPH_IBEAM)


def _draw_glyph(d: bytearray, w: int, h: int, x: int, y: int, glyph: list[str], primary: Color, outline: Color, scale: int = 1) -> None:
    for ri, row in enumerate(glyph):
        for ci, ch in enumerate(row):
            if ch == " ":
                continue
            clr = primary if ch == "#" else outline
            for sy in range(scale):
                for sx in range(scale):
                    _set_pixel(d, w, h, x + ci * scale + sx, y + ri * scale + sy, clr)


def _draw_burst(d: bytearray, w: int, h: int, x: int, y: int, c: Color, r_in: int = 12, r_out: int = 22, rays: int = 8, t: int = 2) -> None:
    for i in range(rays):
        a = (2.0 * math.pi * i) / rays
        cos_a, sin_a = math.cos(a), math.sin(a)
        _draw_line(d, w, h, int(x + r_in * cos_a), int(y + r_in * sin_a), int(x + r_out * cos_a), int(y + r_out * sin_a), c, t)


def _norm(coord: int, extent: int) -> int:
    return int((coord / 1000.0) * extent)


def _movement_trail(d: bytearray, w: int, h: int, x: int, y: int, px: int | None, py: int | None) -> None:
    if px is not None and py is not None and math.hypot(x - px, y - py) > 20:
        _draw_dashed_arrow(d, w, h, px, py, x, y, ACTION_SECONDARY, t=2, dash=6, gap=4, head_len=12)


def _annotate_left_click(d: bytearray, w: int, h: int, x: int, y: int, px: int | None, py: int | None) -> None:
    _movement_trail(d, w, h, x, y, px, py)
    _draw_burst(d, w, h, x, y, ACTION_PRIMARY, 14, 24, 8, 2)
    _draw_glyph(d, w, h, x, y, _GLYPH_CURSOR, ACTION_PRIMARY, ACTION_OUTLINE)


def _annotate_right_click(d: bytearray, w: int, h: int, x: int, y: int, px: int | None, py: int | None) -> None:
    _movement_trail(d, w, h, x, y, px, py)
    p = 20
    _draw_line(d, w, h, x - p, y - p, x + p, y - p, ACTION_PRIMARY, 2)
    _draw_line(d, w, h, x + p, y - p, x + p, y + p, ACTION_PRIMARY, 2)
    _draw_line(d, w, h, x + p, y + p, x - p, y + p, ACTION_PRIMARY, 2)
    _draw_line(d, w, h, x - p, y + p, x - p, y - p, ACTION_PRIMARY, 2)
    _draw_glyph(d, w, h, x, y, _GLYPH_CURSOR_RIGHT, ACTION_PRIMARY, ACTION_OUTLINE)


def _annotate_double_click(d: bytearray, w: int, h: int, x: int, y: int, px: int | None, py: int | None) -> None:
    _movement_trail(d, w, h, x, y, px, py)
    _draw_circle(d, w, h, x, y, 18, ACTION_PRIMARY)
    _draw_circle(d, w, h, x, y, 28, ACTION_PRIMARY)
    _draw_burst(d, w, h, x, y, ACTION_PRIMARY, 30, 38, 8, 2)
    _draw_glyph(d, w, h, x, y, _GLYPH_CURSOR, ACTION_PRIMARY, ACTION_OUTLINE)


def _annotate_drag(d: bytearray, w: int, h: int, x1: int, y1: int, x2: int, y2: int, px: int | None, py: int | None) -> None:
    if px is not None and py is not None and math.hypot(x1 - px, y1 - py) > 20:
        _draw_dashed_arrow(d, w, h, px, py, x1, y1, ACTION_SECONDARY, t=1, dash=4, gap=4, head_len=8)
    _draw_circle(d, w, h, x1, y1, 8, ACTION_PRIMARY, filled=True)
    _draw_dashed_arrow(d, w, h, x1, y1, x2, y2, ACTION_PRIMARY, t=3, dash=10, gap=6, head_len=18, head_deg=25.0)
    _draw_circle(d, w, h, x2, y2, 10, ACTION_PRIMARY)


def _annotate_type(d: bytearray, w: int, h: int, x: int, y: int) -> None:
    _draw_glyph(d, w, h, x - (_IBEAM_W * 2) // 2, y - (_IBEAM_H * 2) // 2, _GLYPH_IBEAM, ACTION_PRIMARY, ACTION_OUTLINE, scale=2)
    _draw_line(d, w, h, x - 15, y + _IBEAM_H + 4, x + 15, y + _IBEAM_H + 4, ACTION_PRIMARY, 2)


def _apply_annotations(rgba: bytes, w: int, h: int, actions: list[str]) -> bytes:
    buf = bytearray(rgba)
    px: int | None = None
    py: int | None = None
    for line in actions:
        paren = line.find("(")
        if paren == -1:
            continue
        name = line[:paren].strip()
        try:
            args: list[object] = eval(f"[{line[paren + 1 : line.rfind(')')]}]", {"__builtins__": {}}, {})
        except Exception:
            continue
        match name:
            case "left_click" if len(args) >= 2:
                x, y = _norm(int(args[0]), w), _norm(int(args[1]), h)
                _annotate_left_click(buf, w, h, x, y, px, py)
                px, py = x, y
            case "right_click" if len(args) >= 2:
                x, y = _norm(int(args[0]), w), _norm(int(args[1]), h)
                _annotate_right_click(buf, w, h, x, y, px, py)
                px, py = x, y
            case "double_left_click" if len(args) >= 2:
                x, y = _norm(int(args[0]), w), _norm(int(args[1]), h)
                _annotate_double_click(buf, w, h, x, y, px, py)
                px, py = x, y
            case "drag" if len(args) >= 4:
                x1 = _norm(int(args[0]), w)
                y1 = _norm(int(args[1]), h)
                x2 = _norm(int(args[2]), w)
                y2 = _norm(int(args[3]), h)
                _annotate_drag(buf, w, h, x1, y1, x2, y2, px, py)
                px, py = x2, y2
            case "type":
                if px is not None and py is not None:
                    _annotate_type(buf, w, h, px, py)
    return bytes(buf)


def capture(actions: list[str], width: int, height: int, marks: bool) -> str:
    sw, sh = _screen_w, _screen_h
    bgra = _capture_bgra(sw, sh)
    if (sw, sh) != (width, height):
        bgra = _downsample_bgra(bgra, sw, sh, width, height)
        sw, sh = width, height
    rgba = _bgra_to_rgba(bgra)
    if marks and actions:
        rgba = _apply_annotations(rgba, sw, sh, actions)
    png = _encode_png(rgba, sw, sh)
    return base64.b64encode(png).decode("ascii")


def main() -> None:
    request = json.loads(sys.stdin.read())
    b64 = capture(
        actions=request.get("actions", []),
        width=request["width"],
        height=request["height"],
        marks=request.get("marks", True),
    )
    sys.stdout.write(b64)
    sys.stdout.flush()


if __name__ == "__main__":
    main()

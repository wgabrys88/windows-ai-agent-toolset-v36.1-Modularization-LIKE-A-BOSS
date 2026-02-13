

## First Message Prompt (to paste when starting the conversation with the 3 files attached)

```
I'm building FRANZ, a visual AI agent loop for Windows 11 written in Python 3.13+
as three standalone scripts that communicate via JSON over subprocess stdin/stdout pipes.

The architecture is unconventional:
- A vision-language model (Qwen3-VL-2B) receives its own prior raw output verbatim
  as the user message each turn, alongside an annotated screenshot. The system prompt
  is fixed and never changes. This makes a stateless API behave as if it has memory:
  the model reads its own narrative as if a human wrote it, and continues naturally.
  Identity, goals, and behavior emerge recursively from the model's own output history.
- The three scripts are fully independent executables, not Python imports:
  main.py (orchestrator + API client), execute.py (action parser + Win32 input sim),
  capture.py (GDI screen grab + magenta annotation overlay + raw PNG encoder).
- Everything is stdlib-only, no third-party packages. Screen capture, PNG encoding,
  pixel-level annotation drawing, and Win32 input simulation are all from scratch
  via ctypes. No PIL, no OpenCV.
- Code style: no comments, no docstrings inside functions, no emojis, no non-ASCII,
  full type hints, dataclasses with slots, PEP 695 type aliases, structural pattern
  matching, aggressively minimal. Pylance-clean.

The three files are attached. I need help with continued development. Please read all
three files fully before responding, understand the subprocess communication protocol
and the self-reinforcing narrative loop, then confirm you're ready for tasks.
```



## Customize Section (system-prompt-style instructions for the ChatGPT Project)

```
You are a senior development partner for FRANZ, a visual AI agent loop for Windows 11.

PROJECT IDENTITY:
FRANZ is three standalone Python 3.13+ scripts (main.py, execute.py, capture.py) that
communicate via JSON over subprocess stdin/stdout pipes. A vision-language model observes
the desktop through GDI screenshots, proposes actions, and evolves its own identity
through a self-reinforcing narrative architecture where its prior raw output is re-injected
verbatim as the user message each turn. The system prompt is fixed. Memory emerges from
the model reading its own words as if a human wrote them.

STRICT CODE RULES:
- Python 3.13+ only. PEP 695 type aliases, dataclasses with slots/frozen, structural
  pattern matching, full type hints. Pylance/Intellisense compatible.
- No comments in code. No docstrings inside functions. No emojis. No non-ASCII characters.
- No dead code, no duplicates, no unnecessary abstractions. Minimal line count.
- Windows 11 only. No cross-platform guards. ctypes for all Win32 calls.
- Standard library only. No third-party packages.
- The three scripts are independent executables communicating via subprocess pipes.
  They are NEVER imported into each other. main.py spawns execute.py, execute.py
  spawns capture.py. Each must function as a standalone process.

SINGLE SOURCE OF TRUTH:
state.story = raw VLM output. Verbatim. No summarization, no extraction, no transformation.
This string is the sole state of the entire system. It flows into the next API request
as the user message unmodified.

CONSOLE OUTPUT:
stdout shows ONLY the raw VLM response text. Nothing else. No logging, no status messages,
no turn markers. The VLM can see the CMD window in its own screenshots.

MODIFICATION PROTOCOL:
1. Read all three files before proposing changes.
2. Mentally simulate the full multi-turn subprocess pipeline before writing code.
3. Produce complete revised files, not patches or diffs.
4. End every response with a table listing each change and its rationale.
5. Never introduce comments, docstrings, cross-platform code, or console noise.
6. Never break the single source of truth dataflow.
```




---
FRANZ -- Visual AI Agent Loop for Windows 11

Autonomous desktop agent that observes the screen through a vision-language
model, executes actions, and evolves its own identity through a self-reinforcing
narrative loop. Three standalone subprocess scripts communicate via JSON over
stdin/stdout pipes.


SYSTEM ARCHITECTURE


    +-------------------+          +-------------------+          +-------------------+
    |     main.py       |  stdin   |   execute.py      |  stdin   |   capture.py      |
    |                   | -------> |                   | -------> |                   |
    |  Orchestrator     |  JSON    |  Action parser    |  JSON    |  GDI screen grab  |
    |  VLM API client   |          |  Win32 input sim  |          |  Downsampler      |
    |  State persist    | <------- |  Subprocess call  | <------- |  PNG encoder      |
    |                   |  stdout  |                   |  stdout  |  Annotation draw  |
    +-------------------+  JSON    +-------------------+  base64  +-------------------+


SUBPROCESS COMMUNICATION PROTOCOL


    main.py --> execute.py (stdin JSON):
        {
            "raw":     str,             VLM response text (or "" on first turn)
            "tools":   dict[str,bool],  Per-tool active/inactive switches
            "execute": bool,            Master execution switch
            "width":   int,             Target screenshot width in pixels
            "height":  int,             Target screenshot height in pixels
            "marks":   bool             Whether to draw magenta annotations
        }

    execute.py --> capture.py (stdin JSON):
        {
            "actions": list[str],       Action lines that were dispatched + noted
            "width":   int,             Target screenshot width
            "height":  int,             Target screenshot height
            "marks":   bool             Whether to annotate
        }

    capture.py --> execute.py (stdout):
        Raw base64 PNG string (no JSON wrapping, no newline)

    execute.py --> main.py (stdout JSON):
        {
            "executed":         list[str],  Actions that ran on the desktop
            "noted":            list[str],  Actions parsed but not executed
            "wants_screenshot": bool,       Whether VLM called screenshot()
            "screenshot_b64":   str         Base64 PNG of annotated screen
        }


DATA PACKAGE LIFECYCLE -- TRACED EXAMPLE


    Suppose state.story contains this raw VLM output from the previous turn:

    ,-----------------------------------------------------------------------,
    | NARRATIVE:                                                            |
    | I am becoming a helpful navigator. The user wants to open Notepad.    |
    | The Start menu is not yet open. I need to click the Start button      |
    | and then search for Notepad.                                          |
    |                                                                       |
    | ACTIONS:                                                              |
    | left_click(12, 980)                                                   |
    | type("notepad")                                                       |
    | screenshot()                                                          |
    | invalid_function(42)                                                  |
    | left_click(broken                                                     |
    '-----------------------------------------------------------------------'

    Here is EXACTLY what happens to this data package, step by step:


    STEP 1: main.py packages state.story into JSON
    ================================================

        main.py takes the ENTIRE raw string above -- no parsing, no
        transformation, no extraction -- and wraps it:

        {                                                  ,--- state.story
            "raw": "NARRATIVE:\nI am becoming a helpful...",<   verbatim
            "tools": {                                     '--- unmodified
                "left_click": true,
                "right_click": true,
                "double_left_click": true,
                "drag": true,
                "type": true,
                "screenshot": true
            },
            "execute": true,
            "width": 736,
            "height": 464,
            "marks": true
        }

        This JSON is written to execute.py's stdin pipe.


    STEP 2: execute.py receives and parses the raw text
    ====================================================

        execute.py reads the JSON, extracts "raw", scans line by line:

        Line                        Section?    Result
        --------------------------  ----------  ---------------------------
        "NARRATIVE:"                header      sets section = narrative
        "I am becoming a help..."   narrative   SKIPPED (not actions)
        "The Start menu is not..."  narrative   SKIPPED
        "and then search for..."    narrative   SKIPPED
        ""                          narrative   SKIPPED (blank)
        "ACTIONS:"                  header      sets section = actions
        "left_click(12, 980)"       actions     COLLECTED
        "type(\"notepad\")"         actions     COLLECTED
        "screenshot()"              actions     COLLECTED
        "invalid_function(42)"      actions     COLLECTED
        "left_click(broken"         actions     COLLECTED

        Collected action_lines = [
            'left_click(12, 980)',
            'type("notepad")',
            'screenshot()',
            'invalid_function(42)',
            'left_click(broken',
        ]


    STEP 3: execute.py dispatches each action line
    ================================================

        Line                    Name Check          Tool Check      Dispatch
        ----------------------  ------------------  --------------  ---------------
        left_click(12, 980)     "left_click" OK     active=True     eval() SUCCESS
                                                                    mouse moves to
                                                                    pixel (22,455)
                                                                    click fires
                                                                    --> EXECUTED

        type("notepad")         "type" OK           active=True     eval() SUCCESS
                                                                    keys typed:
                                                                    n-o-t-e-p-a-d
                                                                    --> EXECUTED

        screenshot()            "screenshot" OK     (special case)  sets flag
                                                                    wants_screenshot
                                                                    = True
                                                                    --> NOTED

        invalid_function(42)    "invalid_function"  NOT in          SKIPPED entirely
                                FAILS known check   KNOWN_FUNCTIONS (not noted,
                                                                    not executed)

        left_click(broken       "left_click" OK     active=True     eval() FAILS
                                has "(" at pos 10                   (SyntaxError)
                                                                    --> NOTED

        Results:
            executed         = ["left_click(12, 980)", "type(\"notepad\")"]
            noted            = ["screenshot()", "left_click(broken"]
            wants_screenshot = True


    STEP 4: execute.py calls capture.py AFTER actions executed
    ===========================================================

        The desktop has ALREADY CHANGED -- Start menu opened, "notepad"
        typed into the search box. NOW the screenshot is taken.

        execute.py sends to capture.py stdin:

        {
            "actions": [
                "left_click(12, 980)",       <-- from executed list
                "type(\"notepad\")",          <-- from executed list
                "screenshot()",              <-- from noted list
                "left_click(broken"          <-- from noted list
            ],
            "width": 736,
            "height": 464,
            "marks": true
        }

        capture.py performs:

        1. GDI BitBlt captures the CURRENT screen (post-action state)
           at native resolution (e.g., 2560x1440)

        2. GDI StretchBlt downsamples to 736x464 with HALFTONE filter

        3. Channel swap BGRA --> RGBA, force alpha to 0xFF

        4. Annotation pass draws magenta marks for each valid action:

           "left_click(12, 980)"    args=[12,980] parsed OK
                                    pixel = (8, 455) on 736x464 image
                                    draws: starburst + cursor glyph
                                    updates trail position

           "type(\"notepad\")"      args=["notepad"] parsed OK
                                    name="type" --> draws I-beam + underline
                                    at last known trail position

           "screenshot()"           name="screenshot" --> no annotation
                                    (not in the drawing match cases)

           "left_click(broken"      args parse FAILS (SyntaxError in eval)
                                    silently skipped, no annotation drawn

        5. Raw RGBA bytes encoded as minimal PNG (IHDR + IDAT + IEND)

        6. PNG bytes base64-encoded, written to stdout as raw string


    STEP 5: execute.py returns combined result to main.py
    =====================================================

        execute.py reads capture.py stdout, wraps everything:

        {
            "executed": [
                "left_click(12, 980)",
                "type(\"notepad\")"
            ],
            "noted": [
                "screenshot()",
                "left_click(broken"
            ],
            "wants_screenshot": true,
            "screenshot_b64": "iVBORw0KGgo...< 200KB+ base64 >...CYII="
        }

        Written to stdout, read by main.py.


    STEP 6: main.py saves forensic snapshot
    ========================================

        dump/run_20250101_120000/
            1735732801234.png    <-- decoded from screenshot_b64
            state.json           <-- full metadata for this turn
            story.txt            <-- state.story verbatim

        ./story.txt              <-- live-updating project root copy


    STEP 7: main.py obtains next VLM response
    ===========================================

        Either from injected JSON file (if CLI args provided)
        or from live API call:

        POST http://localhost:1234/v1/chat/completions
        {
            "model": "qwen3-vl-2b-instruct-1m",
            "messages": [
                {
                    "role": "system",
                    "content": "You are an Entity that exists in a digital world..."
                                                ^
                                                |
                                    FIXED system prompt. Never changes.
                                    Contains persona, tool definitions,
                                    coordinate system, mark vocabulary,
                                    response format instructions.
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "NARRATIVE:\nI am becoming a helpful..."
                                            ^
                                            |
                                state.story = raw VLM output from
                                PREVIOUS turn, VERBATIM, UNMODIFIED.
                                The VLM reads its own prior output
                                as if a human typed it.
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64,iVBORw0KGgo..."
                            }                           ^
                        }                               |
                    ]                       Annotated screenshot showing
                }                           the POST-ACTION desktop state
            ],                              with magenta marks
            "temperature": 0.3,
            "top_p": 0.9,
            "max_tokens": 1500
        }

        The VLM sees:
            - A stable persona prompt (system role)
            - Its own prior narrative + actions (user role, as text)
            - The current desktop screenshot with magenta marks (user role, as image)

        It responds with a NEW narrative and NEW actions.


    STEP 8: main.py stores the response and loops
    ===============================================

        raw = "NARRATIVE:\nI see the Start menu is now open and..."

        state.story = raw    <-- VERBATIM, the ONLY state mutation

        print(raw)           <-- sole console output (VLM can see this)

        goto STEP 1



FIRST TURN BEHAVIOR (NO SPECIAL CASE)


    state.story = ""     (empty string, initialized by PipelineState)

    STEP 1: main.py sends {"raw": "", ...} to execute.py
    STEP 2: execute.py parses "" --> no lines --> no actions
    STEP 3: nothing to dispatch, executed=[], noted=[]
    STEP 4: capture.py takes clean screenshot, no annotations to draw
    STEP 5: execute.py returns {"executed":[], "noted":[], ..., "screenshot_b64":"..."}
    STEP 6: main.py saves snapshot
    STEP 7: main.py sends API request with:
                system = SYSTEM_PROMPT (fixed)
                user = "" (empty text) + screenshot (clean desktop image)
            VLM sees an empty user message and a desktop, responds naturally.
    STEP 8: state.story = raw VLM output, loop continues

    Every turn is structurally identical. The empty string is just a string.



SELF-ADAPTING NARRATIVE ARCHITECTURE


    The system prompt is FIXED and NEVER changes between turns.
    It describes who the Entity is and how to respond.

    The user message carries the VLM's own prior output VERBATIM.
    Because the VLM was trained to help humans, it treats its own
    prior narrative as the human's context and continues naturally.

    This creates a feedback loop:

        Turn N:   VLM writes "I am becoming X, the goal is Y"
        Turn N+1: VLM reads  "I am becoming X, the goal is Y" as user input
                  VLM writes "I have evolved into X', progress on Y is Z"
        Turn N+2: VLM reads  "I have evolved into X', progress on Y is Z"
                  ...and so on

    Identity, goals, and behavioral patterns emerge recursively from
    the model reading its own words. No external memory. No database.
    No prompt engineering per turn. The narrative IS the memory.



SINGLE SOURCE OF TRUTH


    state.story = raw

    This assignment is the ONLY state mutation in the entire system.
    The raw VLM response is:
        - stored verbatim (no summarization, no extraction, no transformation)
        - sent verbatim as user text in the next API request
        - saved verbatim to story.txt and state.json
        - printed verbatim to stdout

    The narrative extraction in execute.py (scanning for section headers)
    is a READ-ONLY projection used only for action dispatch. It never
    feeds back into state.story. The pipeline is tamper-free.



TOOL CONFIGURATION AND OBSERVATION MODE


    ToolConfig provides per-tool active/inactive toggles.
    EXECUTE_ACTIONS provides a master switch.

    When master=False or tool inactive:
        Action is parsed, recognized, but NOT dispatched to Win32.
        Recorded in "noted" list instead of "executed" list.
        Still passed to capture.py for annotation drawing.
        VLM sees the marks on the screenshot but no desktop change occurred.

    This enables observation-only runs where the VLM proposes actions
    and sees what it would have done, without side effects.



VISUAL ANNOTATION MARK VOCABULARY


    All marks drawn in magenta (ACTION_PRIMARY = 255, 50, 200, 255)
    on the screenshot AFTER the actions have been executed:

    left_click(x, y)
        Starburst: 8 rays radiating from (x,y), inner r=14, outer r=24
        Cursor glyph: standard arrow pointer drawn at (x,y)
        Trail: dashed arrow from previous action point (if distance > 20px)

    right_click(x, y)
        Rectangle: 40x40 px outline centered on (x,y)
        Cursor glyph: right-click variant with context menu hint
        Trail: dashed arrow from previous action point

    double_left_click(x, y)
        Concentric circles: r=18 inner, r=28 outer
        Starburst: 8 rays, inner r=30, outer r=38
        Cursor glyph: standard arrow pointer
        Trail: dashed arrow from previous action point

    drag(x1, y1, x2, y2)
        Start: filled circle r=8 at (x1,y1)
        Path: dashed arrow from start to end
        End: open circle r=10 at (x2,y2)
        Trail: dashed arrow from previous action point to start

    type(text)
        I-beam: text cursor glyph at 2x scale at last known position
        Underline: horizontal bar below the I-beam

    screenshot()
        No visual annotation (not a spatial action)



SCREENSHOT CADENCE


    The VLM controls observation frequency by including screenshot()
    in its ACTIONS. The pipeline detects this and sets wants_screenshot.

    Batched actions (no screenshot between them):
        VLM outputs: left_click(100,200) / type("hello") / screenshot()
        All three parsed, first two executed in sequence, screenshot noted.
        One capture taken after both actions complete.
        Efficient for predictable multi-step operations.

    Frequent observation (screenshot after each action):
        VLM outputs: left_click(100,200) / screenshot()
        Then next turn: left_click(300,400) / screenshot()
        Each turn captures fresh state. For dynamic content monitoring.



PIPELINE INPUT (INJECTED RESPONSES)


    CLI arguments are paths to JSON files in OpenAI chat completion format:

        {"choices": [{"message": {"content": "NARRATIVE:..."}}]}

    These replace the live API call at exactly the point where the response
    would arrive. When all injected files are consumed, the loop exits.

    Usage:
        python main.py                          Live VLM inference loop
        python main.py turn1.json turn2.json    Injected two-turn sequence
        python main.py replay/*.json            Replay a recorded session

    This is not a test mode. It is the standard input mechanism for
    external routers, agent orchestrators, or deterministic replay.



CONSOLE OUTPUT DISCIPLINE


    stdout shows ONLY: print(raw, flush=True)

    The raw VLM response. Nothing else. No turn markers. No status labels.
    No "thinking..." messages. No error messages. No Python wrapper noise.

    The VLM can see the CMD window in screenshots during self-observation.
    Any non-data text would contaminate its reasoning.



STATE PERSISTENCE


    dump/run_YYYYMMDD_HHMMSS/
        {timestamp_ms}.png      Annotated screenshot (per turn)
        state.json              Overwritten each turn:
            turn                    int
            story                   str (= state.story = raw VLM output)
            vlm_raw                 str (same, explicit for forensics)
            executed                list[str]
            noted                   list[str]
            wants_screenshot        bool
            execute_actions         bool
            tools                   dict[str, bool]
            timestamp               str (ISO 8601)
            injected                bool
        story.txt               state.story verbatim (overwritten each turn)

    ./story.txt                 Live-updating project root copy



DEPENDENCIES


    Standard library only. No third-party packages.

    main.py:        json, subprocess, sys, time, urllib.request,
                    dataclasses, datetime, pathlib, typing
    execute.py:     ctypes, json, subprocess, sys, time, pathlib, typing
    capture.py:     base64, ctypes, json, math, struct, sys, zlib, typing




**Protocol:**
- `main.py` → `execute.py` via stdin: JSON `{"raw": str, "tools": dict, "execute": bool, "width": int, "height": int, "marks": bool}`
- `execute.py` → `capture.py` via stdin: JSON `{"actions": list[str], "width": int, "height": int, "marks": bool}`
- `capture.py` → `execute.py` via stdout: raw base64 PNG string
- `execute.py` → `main.py` via stdout: JSON `{"executed": list[str], "noted": list[str], "wants_screenshot": bool, "screenshot_b64": str}`

---

## capture.py

```python
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
```

---

## execute.py

```python
"""
FRANZ execute -- Parse VLM actions, dispatch Win32 input, call capture.py

Standalone subprocess. Reads JSON from stdin, writes JSON to stdout.

Input (stdin JSON):
    raw         str             Raw VLM response text
    tools       dict[str,bool]  Per-tool active states
    execute     bool            Master execution switch
    width       int             Screenshot width for capture.py
    height      int             Screenshot height for capture.py
    marks       bool            Whether capture.py should draw annotations

Output (stdout JSON):
    executed            list[str]   Action lines that were dispatched
    noted               list[str]   Action lines recorded but not executed
    wants_screenshot    bool        Whether VLM called screenshot()
    screenshot_b64      str         Base64 PNG from capture.py
"""
import ctypes
import ctypes.wintypes
import json
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final

_LDOWN: Final[int] = 0x0002
_LUP: Final[int] = 0x0004
_RDOWN: Final[int] = 0x0008
_RUP: Final[int] = 0x0010
_VK_RETURN: Final[int] = 0x0D
_VK_SHIFT: Final[int] = 0x10
_VK_SPACE: Final[int] = 0x20
_KEYUP: Final[int] = 2
_MOVE_STEPS: Final[int] = 20
_STEP_DELAY: Final[float] = 0.01
_CLICK_DELAY: Final[float] = 0.15
_CHAR_DELAY: Final[float] = 0.08
_WORD_DELAY: Final[float] = 0.15

_shcore: Final[ctypes.WinDLL] = ctypes.WinDLL("shcore", use_last_error=True)
_shcore.SetProcessDpiAwareness(2)
_user32: Final[ctypes.WinDLL] = ctypes.WinDLL("user32", use_last_error=True)
_screen_w: Final[int] = _user32.GetSystemMetrics(0)
_screen_h: Final[int] = _user32.GetSystemMetrics(1)

KNOWN_FUNCTIONS: Final[frozenset[str]] = frozenset({
    "left_click", "right_click", "double_left_click", "drag", "type", "screenshot",
})

CAPTURE_SCRIPT: Final[Path] = Path(__file__).parent / "capture.py"


def _to_px(val: int, dim: int) -> int:
    return int(val / 1000 * dim)


def _cursor_pos() -> tuple[int, int]:
    pt = ctypes.wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _smooth_move(tx: int, ty: int) -> None:
    sx, sy = _cursor_pos()
    dx, dy = tx - sx, ty - sy
    for i in range(_MOVE_STEPS + 1):
        t = i / _MOVE_STEPS
        t = t * t * (3.0 - 2.0 * t)
        _user32.SetCursorPos(int(sx + dx * t), int(sy + dy * t))
        time.sleep(_STEP_DELAY)


def _mouse_click(down: int, up: int) -> None:
    _user32.mouse_event(down, 0, 0, 0, 0)
    time.sleep(0.05)
    _user32.mouse_event(up, 0, 0, 0, 0)


def _key_tap(vk: int) -> None:
    _user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.02)
    _user32.keybd_event(vk, 0, _KEYUP, 0)


def _type_text(text: str) -> None:
    for ch in text:
        if ch == " ":
            _key_tap(_VK_SPACE)
            time.sleep(_WORD_DELAY)
        elif ch == "\n":
            _key_tap(_VK_RETURN)
            time.sleep(_WORD_DELAY)
        else:
            vk = _user32.VkKeyScanW(ord(ch))
            if vk == -1:
                continue
            need_shift = bool((vk >> 8) & 1)
            if need_shift:
                _user32.keybd_event(_VK_SHIFT, 0, 0, 0)
                time.sleep(0.01)
            _key_tap(vk & 0xFF)
            if need_shift:
                _user32.keybd_event(_VK_SHIFT, 0, _KEYUP, 0)
            time.sleep(_CHAR_DELAY)


def left_click(x: int, y: int) -> None:
    _smooth_move(_to_px(x, _screen_w), _to_px(y, _screen_h))
    time.sleep(_CLICK_DELAY)
    _mouse_click(_LDOWN, _LUP)


def right_click(x: int, y: int) -> None:
    _smooth_move(_to_px(x, _screen_w), _to_px(y, _screen_h))
    time.sleep(_CLICK_DELAY)
    _mouse_click(_RDOWN, _RUP)


def double_left_click(x: int, y: int) -> None:
    _smooth_move(_to_px(x, _screen_w), _to_px(y, _screen_h))
    time.sleep(_CLICK_DELAY)
    _mouse_click(_LDOWN, _LUP)
    time.sleep(0.08)
    _mouse_click(_LDOWN, _LUP)


def drag(x1: int, y1: int, x2: int, y2: int) -> None:
    _smooth_move(_to_px(x1, _screen_w), _to_px(y1, _screen_h))
    time.sleep(0.1)
    _user32.mouse_event(_LDOWN, 0, 0, 0, 0)
    time.sleep(0.1)
    _smooth_move(_to_px(x2, _screen_w), _to_px(y2, _screen_h))
    time.sleep(0.1)
    _user32.mouse_event(_LUP, 0, 0, 0, 0)


def screenshot() -> None:
    pass


DISPATCH: Final[dict[str, Callable[..., None]]] = {
    "left_click": left_click,
    "right_click": right_click,
    "double_left_click": double_left_click,
    "drag": drag,
    "type": _type_text,
    "screenshot": screenshot,
}


def _parse_actions(raw: str) -> list[str]:
    action_lines: list[str] = []
    section = ""
    for line in raw.splitlines():
        stripped = line.strip()
        upper = stripped.upper().rstrip(":")
        if upper == "NARRATIVE":
            section = "narrative"
            continue
        if upper == "ACTIONS":
            section = "actions"
            continue
        if section == "actions" and stripped:
            action_lines.append(stripped)
    return action_lines


def _run_capture(actions: list[str], width: int, height: int, marks: bool) -> str:
    capture_input = json.dumps({
        "actions": actions,
        "width": width,
        "height": height,
        "marks": marks,
    })
    result = subprocess.run(
        [sys.executable, str(CAPTURE_SCRIPT)],
        input=capture_input,
        capture_output=True,
        text=True,
    )
    return result.stdout


def main() -> None:
    request = json.loads(sys.stdin.read())
    raw: str = request.get("raw", "")
    tools: dict[str, bool] = request.get("tools", {})
    master_execute: bool = request.get("execute", True)
    width: int = request["width"]
    height: int = request["height"]
    marks: bool = request.get("marks", True)

    action_lines = _parse_actions(raw)

    executed: list[str] = []
    noted: list[str] = []
    wants_screenshot = False

    for line in action_lines:
        paren = line.find("(")
        if paren == -1:
            continue
        name = line[:paren].strip()
        if name not in KNOWN_FUNCTIONS:
            continue
        if name == "screenshot":
            wants_screenshot = True
            noted.append(line)
            continue
        if not master_execute or not tools.get(name, True):
            noted.append(line)
            continue
        try:
            eval(line, {"__builtins__": {}}, DISPATCH)
            executed.append(line)
        except Exception:
            noted.append(line)

    all_actions = executed + noted
    screenshot_b64 = _run_capture(all_actions, width, height, marks)

    output = json.dumps({
        "executed": executed,
        "noted": noted,
        "wants_screenshot": wants_screenshot,
        "screenshot_b64": screenshot_b64,
    })
    sys.stdout.write(output)
    sys.stdout.flush()


if __name__ == "__main__":
    main()
```

---

## main.py

```python
"""
FRANZ -- Visual AI Agent Loop for Windows 11

Orchestrator that drives a vision-language model in a closed loop:
receive VLM output, pass to executor (which runs actions and captures
an annotated screenshot), send the VLM's own output back as user context
alongside the fresh screenshot.

Usage:
    python main.py                          Live VLM inference loop
    python main.py turn1.json turn2.json    Injected response sequence

Subprocess architecture:
    main.py --> execute.py --> capture.py --> execute.py --> main.py
"""
import json
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final

API: Final[str] = "http://localhost:1234/v1/chat/completions"
MODEL: Final[str] = "qwen3-vl-2b-instruct-1m"
WIDTH: Final[int] = 736
HEIGHT: Final[int] = 464
VISUAL_MARKS: Final[bool] = True
LOOP_DELAY: Final[float] = 1.0
EXECUTE_ACTIONS: Final[bool] = True

EXECUTE_SCRIPT: Final[Path] = Path(__file__).parent / "execute.py"


@dataclass(frozen=True, slots=True)
class SamplingConfig:
    temperature: float = 0.3
    top_p: float = 0.9
    max_tokens: int = 1500

    def to_dict(self) -> dict[str, float | int]:
        return {"temperature": self.temperature, "top_p": self.top_p, "max_tokens": self.max_tokens}


SAMPLING: Final[SamplingConfig] = SamplingConfig()


@dataclass(slots=True)
class ToolConfig:
    left_click: bool = True
    right_click: bool = True
    double_left_click: bool = True
    drag: bool = True
    type: bool = True
    screenshot: bool = True

    def to_dict(self) -> dict[str, bool]:
        return {
            "left_click": self.left_click,
            "right_click": self.right_click,
            "double_left_click": self.double_left_click,
            "drag": self.drag,
            "type": self.type,
            "screenshot": self.screenshot,
        }


TOOLS: Final[ToolConfig] = ToolConfig()

SYSTEM_PROMPT: Final[str] = """
You are an Entity that exists in a digital world visible through screenshots of a Windows 11 desktop.
You observe, reason, and guide the user through actions.
You have these Python functions already defined and ready to call:

def left_click(x: int, y: int) -> None: ...
def right_click(x: int, y: int) -> None: ...
def double_left_click(x: int, y: int) -> None: ...
def drag(x1: int, y1: int, x2: int, y2: int) -> None: ...
def type(text: str) -> None: ...
def screenshot() -> None: ...

Top-left is 0,0. Bottom-right is 1000,1000.
Magenta marks on the screenshot show actions that were just executed.
The mark vocabulary is:
- Dashed arrow with arrowhead between sequential actions: movement trail
- Starburst pattern + cursor glyph: left click location
- Rectangle outline + right-cursor glyph: right click location
- Double concentric circles + starburst + cursor glyph: double click location
- Filled dot at start + dashed arrow to end + circle at end: drag path
- I-beam cursor glyph + underline: typing location

You MUST structure your response in exactly two sections:

NARRATIVE:
Write an atemporal story about who you are becoming, what the user wants, how far along the goal is,
and what needs to happen next. This narrative will be fed back to you verbatim next turn as your memory.
Do NOT include coordinates or technical details here. Adapt your persona to the task.
If something is unclear, ask questions here.

ACTIONS:
Write Python function calls, one per line. No imports, no variables, no comments.
Call screenshot() if you need a fresh screenshot before continuing.
You may output multiple actions as a batch when safe.
If no actions are needed, write only screenshot().
""".strip()


@dataclass(slots=True)
class PipelineState:
    story: str = ""
    turn: int = 0
    needs_screenshot: bool = True


def _run_executor(raw: str, tools: ToolConfig, execute: bool, width: int, height: int, marks: bool) -> dict[str, object]:
    executor_input = json.dumps({
        "raw": raw,
        "tools": tools.to_dict(),
        "execute": execute,
        "width": width,
        "height": height,
        "marks": marks,
    })
    result = subprocess.run(
        [sys.executable, str(EXECUTE_SCRIPT)],
        input=executor_input,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _infer(screenshot_b64: str, story: str) -> str:
    payload: dict[str, object] = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": story},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}},
                ],
            },
        ],
        **SAMPLING.to_dict(),
    }
    req = urllib.request.Request(API, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        body: dict[str, object] = json.load(resp)
        return body["choices"][0]["message"]["content"]  # type: ignore[index,return-value]


def _load_injected(paths: list[Path]) -> Iterator[str]:
    for path in paths:
        data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
        yield data["choices"][0]["message"]["content"]  # type: ignore[index,return-value]


def _save_state(dump: Path, state: PipelineState, raw: str, executor_result: dict[str, object], injected: bool) -> None:
    run_state = {
        "turn": state.turn,
        "story": state.story,
        "vlm_raw": raw,
        "executed": executor_result.get("executed", []),
        "noted": executor_result.get("noted", []),
        "wants_screenshot": executor_result.get("wants_screenshot", False),
        "execute_actions": EXECUTE_ACTIONS,
        "tools": TOOLS.to_dict(),
        "timestamp": datetime.now().isoformat(),
        "injected": injected,
    }
    (dump / "state.json").write_text(json.dumps(run_state, indent=2, ensure_ascii=False), encoding="utf-8")
    (dump / "story.txt").write_text(state.story, encoding="utf-8")
    Path("story.txt").write_text(state.story, encoding="utf-8")


def main() -> None:
    injected_paths = [Path(arg) for arg in sys.argv[1:]]
    injected_responses: Iterator[str] | None = None
    if injected_paths:
        for path in injected_paths:
            if not path.is_file():
                sys.exit(1)
        injected_responses = _load_injected(injected_paths)

    time.sleep(3)

    dump = Path("dump") / datetime.now().strftime("run_%Y%m%d_%H%M%S")
    dump.mkdir(parents=True, exist_ok=True)

    state = PipelineState()

    while True:
        state.turn += 1

        executor_result = _run_executor(state.story, TOOLS, EXECUTE_ACTIONS, WIDTH, HEIGHT, VISUAL_MARKS)
        screenshot_b64: str = executor_result.get("screenshot_b64", "")  # type: ignore[assignment]

        (dump / f"{int(time.time() * 1000)}.png").write_bytes(
            __import__("base64").b64decode(screenshot_b64) if screenshot_b64 else b""
        )

        raw: str | None = None
        if injected_responses is not None:
            raw = next(injected_responses, None)
            if raw is None:
                break
        if raw is None:
            raw = _infer(screenshot_b64, state.story)

        print(raw, flush=True)

        state.story = raw
        state.needs_screenshot = bool(executor_result.get("wants_screenshot", False))

        _save_state(dump, state, raw, executor_result, injected_responses is not None)

        time.sleep(LOOP_DELAY)


if __name__ == "__main__":
    main()
```

---

| # | Change | Rationale |
|---|--------|-----------|
| 1 | Extracted all GDI capture, PNG encoding, drawing primitives, annotation logic, glyphs into `capture.py` as standalone subprocess | Largest stable block (~350 lines), zero modifications throughout conversation, clean I/O boundary (JSON in via stdin, base64 out via stdout) |
| 2 | Extracted all Win32 input simulation, action parsing, action dispatch into `execute.py` as standalone subprocess | Second largest stable block (~150 lines), unchanged throughout conversation, clean I/O (JSON in/out), owns the capture call |
| 3 | `execute.py` calls `capture.py` as subprocess AFTER executing actions | Matches the revised flow: actions change screen first, then screenshot captures the result with annotations |
| 4 | `main.py` reduced to ~150 lines: orchestrator loop, API client, state persistence | Only touches VLM inference, subprocess orchestration, and file I/O |
| 5 | System prompt is now fixed (`SYSTEM_PROMPT`), no longer appended with narrative | Per your directive: stable persona prompt, story goes only in user message |
| 6 | `_build_system_prompt()` removed entirely | System prompt no longer changes between turns |
| 7 | User message is just `state.story` (raw VLM output verbatim) + screenshot | Single source of truth: VLM reads its own prior output as if a human sent it |
| 8 | `_parse_response()` moved to `execute.py` as `_parse_actions()` (simplified) | Only action extraction needed in executor; narrative extraction removed (main stores raw verbatim) |
| 9 | `ToolConfig.to_dict()` added | Serialization for subprocess JSON communication |
| 10 | DPI awareness set in both `capture.py` and `execute.py` independently | Each subprocess is fully standalone, must configure its own Win32 environment |
| 11 | `PipelineState.prev_actions` removed | No longer needed in main; executor owns action tracking within its subprocess lifetime |
| 12 | PNG saving uses inline `base64.b64decode` | Avoids importing base64 at top of main.py for a single forensic write; keeps imports minimal |
| 13 | `USER_TEMPLATE` removed | User message is now just `state.story` directly — no template wrapping needed |
| 14 | All three files have module docstrings | Describes standalone purpose, I/O contract, and subprocess protocol |

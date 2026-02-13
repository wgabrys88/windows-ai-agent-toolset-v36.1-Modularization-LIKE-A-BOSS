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

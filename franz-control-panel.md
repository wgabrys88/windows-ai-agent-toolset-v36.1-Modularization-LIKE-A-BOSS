
# FRANZ Panel — Acting as a Fake OpenAI API Server

1. `main.py` calls `_infer()` which sends a POST to `http://localhost:1234/v1/chat/completions`
2. `main.py` calls `_run_executor()` which runs `execute.py` as subprocess
3. The VLM response comes from the API server, not from injected files

So the panel should **replace LM Studio** — it **is** the API server at `/v1/chat/completions`. When `main.py` hits that endpoint, the panel holds the request open, shows you the screenshot (which `main.py` sent as the base64 image in the message), waits for you to type a response in the browser, and returns it as the OpenAI-format JSON response.

No injected files. No subprocess wrapping. `main.py` runs normally and thinks it's talking to a real VLM.

---

## `panel.py`

```python
"""
FRANZ Web Control Panel — Fake OpenAI API + Browser UI

Replaces LM Studio. main.py runs normally and POSTs to /v1/chat/completions.
This server:
  1. Receives the request (which includes the base64 screenshot)
  2. Pushes the screenshot + story to the browser via SSE
  3. Waits for you to type the VLM response in the browser
  4. Returns it as an OpenAI-compatible JSON response to main.py

Usage:
    1. Change API in main.py to "http://localhost:8088/v1/chat/completions"
       (or set PORT below to 1234 to impersonate LM Studio directly)
    2. python panel.py
    3. Open http://localhost:8088 in browser
    4. python main.py   (in another terminal — no arguments needed)
    5. Each turn: see the screenshot, type your response, hit Send
"""

import json
import threading
import time
import queue
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

HOST = "0.0.0.0"
PORT = 1234  # Same port as LM Studio so main.py needs zero changes

# ── Shared state between the API handler and the browser UI ──────

# API thread puts the incoming request here for the browser to see
pending_request: queue.Queue = queue.Queue(maxsize=1)

# Browser thread puts the human-typed response here for the API to return
pending_response: queue.Queue = queue.Queue(maxsize=1)

# SSE subscribers (browser tabs listening for new turns)
sse_clients: list[queue.Queue] = []
sse_lock = threading.Lock()

turn_counter = 0


def broadcast_sse(event: str, data: dict) -> None:
    """Send an SSE event to all connected browsers."""
    payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    with sse_lock:
        dead = []
        for q in sse_clients:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)
        for q in dead:
            sse_clients.remove(q)


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FRANZ Panel</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:#111;color:#ddd;font-family:monospace;font-size:14px}
#wrap{max-width:960px;margin:0 auto;padding:12px;display:flex;flex-direction:column;gap:10px;min-height:100%}
h1{font-size:18px;color:#0f0;text-align:center;padding:6px 0}
textarea{width:100%;height:200px;background:#1a1a1a;color:#eee;border:1px solid #333;padding:10px;font-family:monospace;font-size:13px;resize:vertical;border-radius:4px}
textarea:focus{outline:none;border-color:#0f0}
button{padding:10px 24px;background:#0f0;color:#000;border:none;font-family:monospace;font-size:14px;font-weight:bold;cursor:pointer;border-radius:4px}
button:disabled{background:#333;color:#666;cursor:not-allowed}
button:hover:not(:disabled){background:#0c0}
.sb{background:#222;color:#aaa;font-size:12px;padding:6px 12px;border:1px solid #333}
.sb:hover:not(:disabled){background:#333;color:#eee}
#status{padding:6px 10px;border-radius:4px;font-size:13px;min-height:28px;display:flex;align-items:center;gap:8px}
.waiting{background:#331;color:#fa0}
.ready{background:#131;color:#0f0}
.idle{background:#1a1a1a;color:#666}
#screenshot-box{text-align:center;background:#0a0a0a;border:1px solid #222;border-radius:4px;padding:8px;min-height:60px}
#screenshot-box img{max-width:100%;height:auto;border:1px solid #333;border-radius:2px}
#screenshot-box .empty{color:#555;padding:40px 0}
#story-box{background:#1a1a1a;border:1px solid #222;border-radius:4px;padding:10px;white-space:pre-wrap;word-break:break-word;max-height:200px;overflow-y:auto;font-size:12px;color:#aaa}
#story-box:empty::after{content:"Waiting for main.py to connect...";color:#555}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
label{color:#888;font-size:12px}
#turn{color:#0f0}
#model-info{color:#555;font-size:11px}
</style>
</head>
<body>
<div id="wrap">
<h1>🤖 FRANZ — Human VLM Panel</h1>

<div id="status" class="idle">⏸ Idle — start main.py to begin</div>

<div class="row">
  <span>Turn: <span id="turn">0</span></span>
  <span id="model-info"></span>
</div>

<label>Story / Context sent by main.py:</label>
<div id="story-box"></div>

<label>Screenshot (from main.py request):</label>
<div id="screenshot-box"><div class="empty">No screenshot yet — waiting for main.py</div></div>

<label>Your VLM Response (NARRATIVE + ACTIONS):</label>
<textarea id="input" spellcheck="false" disabled placeholder="Waiting for main.py to send a turn..."></textarea>

<div class="row">
  <button id="send" onclick="sendResponse()" disabled>▶ Send Response</button>
  <button class="sb" onclick="ins('ss')">📷 screenshot()</button>
  <button class="sb" onclick="ins('click')">🖱 left_click</button>
  <button class="sb" onclick="ins('rclick')">🖱 right_click</button>
  <button class="sb" onclick="ins('dclick')">🖱🖱 dbl_click</button>
  <button class="sb" onclick="ins('type')">⌨ type</button>
  <button class="sb" onclick="ins('drag')">↔ drag</button>
</div>

</div>

<script>
let turn=0;
let awaitingResponse=false;

const tpl={
  ss:"NARRATIVE:\nI observe the current state of the screen.\n\nACTIONS:\nscreenshot()",
  click:"NARRATIVE:\nI will click on the target element.\n\nACTIONS:\nleft_click(500, 500)",
  rclick:"NARRATIVE:\nI will right-click to open context menu.\n\nACTIONS:\nright_click(500, 500)",
  dclick:"NARRATIVE:\nI will double-click to open the item.\n\nACTIONS:\ndouble_left_click(500, 500)",
  type:'NARRATIVE:\nI will type text into the focused field.\n\nACTIONS:\ntype("hello")',
  drag:"NARRATIVE:\nI will drag from point A to point B.\n\nACTIONS:\ndrag(100, 100, 500, 500)"
};

function ins(k){
  const ta=document.getElementById('input');
  if(!ta.disabled) ta.value=tpl[k];
}

function setStatus(cls,msg){
  const el=document.getElementById('status');
  el.className=cls;
  el.textContent=msg;
}

async function sendResponse(){
  const ta=document.getElementById('input');
  const content=ta.value.trim();
  if(!content){return}
  document.getElementById('send').disabled=true;
  ta.disabled=true;
  awaitingResponse=false;
  setStatus('idle','⏳ Sending response to main.py...');

  try{
    await fetch('/human_response',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({content})
    });
    setStatus('idle','⏸ Response sent. Waiting for next turn...');
  }catch(e){
    setStatus('waiting','❌ Failed to send: '+e.message);
    ta.disabled=false;
    document.getElementById('send').disabled=false;
  }
}

// SSE — listen for incoming turns from main.py
const evs=new EventSource('/events');

evs.addEventListener('new_turn',function(e){
  const data=JSON.parse(e.data);
  turn=data.turn||turn+1;
  document.getElementById('turn').textContent=turn;
  document.getElementById('model-info').textContent=data.model||'';

  // Story
  const sb=document.getElementById('story-box');
  sb.textContent=data.story||'(empty story)';

  // Screenshot
  const box=document.getElementById('screenshot-box');
  if(data.screenshot_b64){
    box.innerHTML='<img src="data:image/png;base64,'+data.screenshot_b64+'" alt="turn '+turn+'">';
  }else{
    box.innerHTML='<div class="empty">No screenshot in this request</div>';
  }

  // Enable input
  const ta=document.getElementById('input');
  ta.disabled=false;
  ta.value='';
  ta.focus();
  document.getElementById('send').disabled=false;
  awaitingResponse=true;
  setStatus('ready','🟢 main.py is waiting for your response — type and send');
});

evs.addEventListener('ping',function(e){});

evs.onerror=function(){
  setStatus('waiting','⚠️ SSE disconnected — reconnecting...');
};

// Ctrl+Enter to send
document.getElementById('input').addEventListener('keydown',e=>{
  if(e.ctrlKey&&e.key==='Enter'){e.preventDefault();sendResponse()}
});
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # Show API calls in terminal for debugging
        msg = fmt % args
        if "/v1/" in msg or "error" in msg.lower():
            print(f"  [HTTP] {msg}")

    # ── Browser: serve the HTML page ────────────────────────────

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/events":
            self._handle_sse()
            return

        # Serve HTML for any other GET
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(HTML.encode())

    # ── main.py: OpenAI-compatible chat completions endpoint ────

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/v1/chat/completions":
            self._handle_completions()
            return

        if path == "/human_response":
            self._handle_human_response()
            return

        self.send_response(404)
        self.end_headers()

    def _handle_completions(self):
        """
        Receives the request from main.py _infer().
        Extracts the screenshot and story from the messages.
        Pushes them to the browser via SSE.
        Blocks until the human types a response.
        Returns it in OpenAI format.
        """
        global turn_counter

        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length)

        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error":"invalid json"}')
            return

        turn_counter += 1

        # Extract data from OpenAI-format request
        messages = body.get("messages", [])
        model = body.get("model", "")
        screenshot_b64 = ""
        story = ""

        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    # Multi-modal message
                    for part in content:
                        if isinstance(part, dict):
                            if part.get("type") == "text":
                                story = part.get("text", "")
                            elif part.get("type") == "image_url":
                                url = part.get("image_url", {}).get("url", "")
                                if url.startswith("data:image/png;base64,"):
                                    screenshot_b64 = url[len("data:image/png;base64,"):]
                elif isinstance(content, str):
                    story = content

        # Push to browser
        broadcast_sse("new_turn", {
            "turn": turn_counter,
            "model": model,
            "story": story,
            "screenshot_b64": screenshot_b64,
        })

        print(f"  [Turn {turn_counter}] Waiting for human response...")

        # Drain any stale response
        while not pending_response.empty():
            try:
                pending_response.get_nowait()
            except queue.Empty:
                break

        # Block until human responds in browser
        human_content = pending_response.get()  # blocks

        print(f"  [Turn {turn_counter}] Human responded ({len(human_content)} chars)")

        # Build OpenAI-compatible response
        response = {
            "id": f"franz-{turn_counter}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model or "human-vlm",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": human_content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }

        payload = json.dumps(response, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_human_response(self):
        """Browser sends the human-typed VLM response here."""
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        content = body.get("content", "")

        pending_response.put(content)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def _handle_sse(self):
        """Server-Sent Events stream for the browser."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q: queue.Queue = queue.Queue(maxsize=50)
        with sse_lock:
            sse_clients.append(q)

        try:
            while True:
                try:
                    data = q.get(timeout=15)
                    self.wfile.write(data.encode())
                    self.wfile.flush()
                except queue.Empty:
                    # Send keepalive ping
                    self.wfile.write(b"event: ping\ndata: {}\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with sse_lock:
                if q in sse_clients:
                    sse_clients.remove(q)


class ThreadedHTTPServer(HTTPServer):
    """Handle each request in a new thread so SSE doesn't block API calls."""
    def process_request(self, request, client_address):
        t = threading.Thread(target=self._handle, args=(request, client_address))
        t.daemon = True
        t.start()

    def _handle(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


def main():
    server = ThreadedHTTPServer((HOST, PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"╔═══════════════════════════════════════════════════╗")
    print(f"║   FRANZ — Human VLM Panel (Fake OpenAI Server)   ║")
    print(f"║   {url:<47s} ║")
    print(f"╚═══════════════════════════════════════════════════╝")
    print(f"")
    print(f"  1. Open {url} in your browser")
    print(f"  2. Run: python main.py  (in another terminal)")
    print(f"  3. Each turn: see screenshot, type response, send")
    print(f"")
    print(f"  main.py API target: http://localhost:{PORT}/v1/chat/completions")
    print(f"  Press Ctrl+C to stop.\n")

    try:
        import webbrowser
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    except Exception:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
```

---

## How it works

```
┌─────────────────┐          ┌──────────────────────────┐         ┌──────────┐
│    main.py      │          │       panel.py            │         │ Browser  │
│                 │          │   (port 1234)             │         │          │
│ _run_executor() │          │                           │  SSE    │          │
│  ↓ screenshot   │          │                           │ ◄───────│ /events  │
│                 │  POST    │ /v1/chat/completions      │         │          │
│ _infer() ──────────────────▶  extract screenshot_b64  │         │          │
│                 │          │  extract story             │ push   │          │
│                 │          │  ─── broadcast SSE ────────────────▶│ show img │
│                 │          │                           │         │ show ctx │
│   (blocked)     │          │  ─── block waiting ───    │         │          │
│                 │          │                           │  POST   │          │
│                 │          │ /human_response ◄──────────────────│ [Send]   │
│                 │          │                           │         │          │
│                 │  ◄───────── return OpenAI JSON ──    │         │          │
│ raw = response  │          │                           │         │          │
│ print(raw)      │          │                           │         │          │
│ loop ──────────▶│          │                           │         │          │
└─────────────────┘          └──────────────────────────┘         └──────────┘
```

## Key points

| Detail | Explanation |
|---|---|
| **Zero changes to main.py** | Set `PORT = 1234` in panel.py (default) — same as LM Studio. Or change `API` in main.py to match |
| **No injected files** | main.py runs with no arguments, in its normal live loop |
| **Screenshot flows naturally** | main.py puts it in the `image_url` message → panel extracts it → SSE pushes to browser → `<img>` tag |
| **Blocking request** | `/v1/chat/completions` blocks until you type and click Send — main.py just waits like it would for a slow model |
| **Threaded server** | SSE connections, API calls, and browser POSTs all run on separate threads |
| **Works everywhere** | Plain HTML5 + SSE + fetch — Android Chrome, desktop browsers, no websockets needed |
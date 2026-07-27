"""Phone-as-touchpad: a tiny web remote served over the LAN.

On a Linux phone the phone screen itself will be the touchpad (the Nebula
pattern); until beamshell runs *on* the phone, and for laptop-kiosk sessions,
any phone browser works: `beamshell run --remote 8577`, open the printed URL,
and the page becomes a touchpad speaking the shell's shared event vocabulary
(tap=open, horizontal swipe=prev/next|size, vertical swipe=push/pull, buttons
for back/recenter, plus a text field that types into text-mode apps like the
terminal).

Transport is deliberately boring: one HTML page, gestures classified client-side
in ~30 lines of JS, events POSTed as JSON. No websockets, no dependencies.
Latency is fine for discrete events (this is not a pointer stream — yet).

SECURITY: anyone on your LAN who can reach the port can send events and text.
It's opt-in (--remote), off by default; don't enable it on hostile networks.
The server binds all interfaces so the phone can reach it.
"""
from __future__ import annotations

import json
import socket
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALLOWED_EVENTS = {"prev", "next", "up", "down", "activate", "back", "recenter"}

PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>beamshell remote</title>
<style>
 body { margin:0; background:#0a0e14; color:#dce6ee; font-family:sans-serif;
        display:flex; flex-direction:column; height:100dvh; }
 #pad { flex:1; display:flex; align-items:center; justify-content:center;
        color:#3d5666; font-size:1.1em; user-select:none; touch-action:none; }
 #row { display:flex; gap:8px; padding:10px; }
 button { flex:1; padding:14px 0; font-size:1em; background:#16222e;
          color:#cfe3ee; border:1px solid #2c485a; border-radius:10px; }
 #text { display:flex; gap:8px; padding:0 10px 12px; }
 #text input { flex:1; padding:10px; font-size:1em; background:#101820;
               color:#dce6ee; border:1px solid #2c485a; border-radius:10px; }
 .flash { background:#14303e !important; }
</style></head><body>
<div id="pad">tap = open &nbsp;·&nbsp; swipe = navigate / size / distance</div>
<div id="row">
 <button data-ev="back">back</button>
 <button data-ev="recenter">recenter</button>
 <button data-ev="activate">open</button>
</div>
<div id="text"><input id="t" placeholder="type into the terminal…" autocomplete="off">
 <button id="send">send</button></div>
<script>
 const post = body => fetch("/event", {method:"POST",
   headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
 const pad = document.getElementById("pad");
 let x0=0, y0=0, t0=0;
 pad.addEventListener("touchstart", e => { const t=e.touches[0];
   x0=t.clientX; y0=t.clientY; t0=Date.now(); e.preventDefault(); });
 pad.addEventListener("touchend", e => {
   const t=e.changedTouches[0], dx=t.clientX-x0, dy=t.clientY-y0;
   const ax=Math.abs(dx), ay=Math.abs(dy);
   let ev=null;
   if (ax<18 && ay<18 && Date.now()-t0<400) ev="activate";
   else if (ax>=48 && ay<=ax*0.6) ev=dx>0?"next":"prev";
   else if (ay>=48 && ax<=ay*0.6) ev=dy>0?"down":"up";
   if (ev){ post({ev}); pad.classList.add("flash");
            setTimeout(()=>pad.classList.remove("flash"),120); }
   e.preventDefault(); });
 document.querySelectorAll("#row button").forEach(b =>
   b.addEventListener("click", () => post({ev:b.dataset.ev})));
 const input = document.getElementById("t");
 const send = () => { if(input.value){ post({text:input.value+"\\r"}); input.value=""; } };
 document.getElementById("send").addEventListener("click", send);
 input.addEventListener("keydown", e => { if(e.key==="Enter"){ send(); e.preventDefault(); }});
</script></body></html>"""


def lan_ip() -> str:
    """Best-effort LAN address for the printed URL."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 80))     # no traffic sent; picks the default route
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


class RemoteServer:
    """Serve the touchpad page; queue validated events/text for the render loop.

    Same consumer interface as DaydreamController: poll_events() / poll_text().
    """

    def __init__(self, port: int = 8577, bind: str = "0.0.0.0"):
        self._events: deque[str] = deque(maxlen=64)
        self._text: deque[str] = deque(maxlen=64)
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):    # keep the shell's stdout clean
                pass

            def do_GET(self):
                body = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if self.path != "/event":
                    self.send_error(404)
                    return
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    msg = json.loads(self.rfile.read(n))
                except (ValueError, json.JSONDecodeError):
                    self.send_error(400)
                    return
                outer._enqueue(msg)
                self.send_response(204)
                self.end_headers()

        self._httpd = ThreadingHTTPServer((bind, port), Handler)
        self.port = self._httpd.server_port
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="beamshell-remote", daemon=True)
        self._thread.start()

    def _enqueue(self, msg) -> None:
        if not isinstance(msg, dict):
            return
        with self._lock:
            ev = msg.get("ev")
            if ev in ALLOWED_EVENTS:
                self._events.append(ev)
            text = msg.get("text")
            if isinstance(text, str) and 0 < len(text) <= 1024:
                self._text.append(text)

    def url(self) -> str:
        return f"http://{lan_ip()}:{self.port}/"

    def poll_events(self) -> list[str]:
        with self._lock:
            out = list(self._events)
            self._events.clear()
        return out

    def poll_text(self) -> str:
        with self._lock:
            out = "".join(self._text)
            self._text.clear()
        return out

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

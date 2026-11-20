#!/usr/bin/env python3
"""Obtain an Avy session token with your own BankID, from the terminal.

Starts a local web page at http://127.0.0.1:8765/ showing a LIVE BankID QR
(the official QR rotates every second, so a static image does not work).
Scan it with your BankID app and approve. The token is then written to
AVY_TOKEN_FILE (default ~/.avy/token.json) with mode 0600.

Requires: pip install qrcode pillow
"""
import base64
import datetime
import io
import json
import os
import stat
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import qrcode

API_BASE = os.environ.get("AVY_API_BASE", "https://api.avy.se/api")
TOKEN_FILE = Path(os.environ.get("AVY_TOKEN_FILE", "~/.avy/token.json")).expanduser()
PORT = int(os.environ.get("AVY_LOGIN_PORT", "8765"))
TIMEOUT = int(os.environ.get("AVY_LOGIN_TIMEOUT", "300"))
CAP_FILE = Path(os.environ.get("AVY_CAPABILITIES_FILE", "~/.avy/capabilities.json")).expanduser()

HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Avy login</title><style>
body{font-family:sans-serif;text-align:center;margin:2rem}
img{width:360px;height:360px;image-rendering:pixelated}
</style></head><body><h2>Avy BankID login</h2>
<p>Scan with the BankID app and approve. refreshes every second.</p>
<img id="qr" src="/qr.png"><p id="status">Waiting...</p>
<script>
const img=document.getElementById('qr');
setInterval(()=>{img.src='/qr.png?t='+Date.now();},1000);
setInterval(async()=>{const r=await fetch('/status');
document.getElementById('status').textContent=await r.text();},2000);
</script></body></html>"""


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API_BASE + path,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
    try:
        return json.loads(raw)
    except ValueError:
        return {"raw": raw}


def main():
    if "--help" in os.sys.argv or "-h" in os.sys.argv:
        print(__doc__)
        return
    auth = call("POST", "/v1/auth/bankid/auth", {})
    if "order_ref" not in auth:
        raise SystemExit(f"Could not start BankID order: {auth}")
    order_ref = auth["order_ref"]
    qr_token = auth["qr_start_token"]
    status_text = ["Waiting for BankID..."]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/qr.png"):
                payload = call("GET", f"/v1/auth/bankid/qr/{qr_token}").get("qr_code", "")
                buf = io.BytesIO()
                qrcode.make(payload).save(buf, format="PNG")
                body = buf.getvalue()
                content_type = "image/png"
            elif self.path.startswith("/status"):
                body, content_type = status_text[0].encode(), "text/plain"
            else:
                body, content_type = HTML.encode(), "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Open http://127.0.0.1:{PORT}/ and scan the live QR with BankID.", flush=True)
    print("Confirm that the BankID app shows Avy as the relying party.", flush=True)

    deadline = time.time() + TIMEOUT
    last = None
    try:
        while time.time() < deadline:
            result = call("POST", "/v1/auth/bankid/collect", {"order_ref": order_ref})
            status = result.get("status")
            if status != last:
                print(f"BankID: {status} ({result.get('hint_code', '')})", flush=True)
                status_text[0] = f"BankID: {status} / {result.get('hint_code', '')}"
                last = status
            if status == "complete":
                break
            if status in ("failed", "cancelled"):
                raise SystemExit(f"BankID order failed: {result}")
            time.sleep(1)
        else:
            raise SystemExit("BankID approval timed out")
    finally:
        server.shutdown()

    token = call("POST", "/v1/auth/bankid/login", {"order_ref": order_ref})
    if "token" not in token:
        raise SystemExit(f"Login failed: {token}")
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(token, indent=2))
    TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(f"OK. Token written to {TOKEN_FILE} (mode 0600).")
    print("Treat it as a password; never commit or share it.")

    save_capabilities(token["token"])


def save_capabilities(bearer):
    """Record enabled features once, so later sessions need no re-probing.

    Stores no personal data: only feature flags, form type names/ids and the
    token expiry timestamp. Never stores the token itself.
    """
    def authed(path):
        req = urllib.request.Request(
            API_BASE + path, headers={"Authorization": "Bearer " + bearer,
                                      "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)

    expires = None
    try:
        segment = bearer.split(".")[1]
        segment += "=" * (-len(segment) % 4)
        expires = json.loads(base64.urlsafe_b64decode(segment)).get("exp")
    except (IndexError, ValueError):
        pass

    data = {
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "token_expires_at": (
            datetime.datetime.fromtimestamp(expires, datetime.timezone.utc).isoformat()
            if expires else None
        ),
    }
    try:
        features = authed("/v1/features")
        data["flags"] = sorted(features.get("flags", []))
        data["config_keys"] = sorted((features.get("config") or {}).keys())
    except Exception as exc:
        data["flags_error"] = str(exc)
    try:
        data["form_types"] = [
            {"form_type_id": t.get("form_type_id"), "name": t.get("name")}
            for t in authed("/v2/contact-form/type")
        ]
    except Exception as exc:
        data["form_types_error"] = str(exc)

    try:
        CAP_FILE.parent.mkdir(parents=True, exist_ok=True)
        CAP_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        CAP_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
        print(f"Capability map saved to {CAP_FILE}")
    except OSError as exc:
        print(f"Warning: could not save capability map: {exc}")


if __name__ == "__main__":
    main()

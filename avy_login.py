#!/usr/bin/env python3
"""Log in to Avy with your own BankID using a live QR on localhost."""
import argparse
import os
import sys
import threading
import time
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

from avy import ApiError, CAP_FILE, TOKEN_FILE, call, refresh_capabilities, write_private_json

PORT = int(os.environ.get("AVY_LOGIN_PORT", "8765"))
TIMEOUT = int(os.environ.get("AVY_LOGIN_TIMEOUT", "300"))

HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Avy login</title><style>
body{font-family:sans-serif;text-align:center;margin:2rem}
img{width:360px;height:360px;image-rendering:pixelated}
</style></head><body><h2>Avy BankID login</h2>
<p>Scan with the BankID app and approve. The QR refreshes every second.</p>
<img id="qr" src="/qr.svg" alt="Live BankID QR code"><p id="status">Waiting...</p>
<script>
const img=document.getElementById('qr');
setInterval(()=>{img.src='/qr.svg?t='+Date.now();},1000);
setInterval(async()=>{const r=await fetch('/status');
document.getElementById('status').textContent=await r.text();},2000);
</script></body></html>"""


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        _login()
    except (ApiError, OSError) as exc:
        raise SystemExit(str(exc)) from None


def _login():
    import qrcode
    from qrcode.image.svg import SvgPathFillImage

    request = partial(call, authenticated=False)
    auth = request("POST", "/v1/auth/bankid/auth", {})
    if not isinstance(auth, dict) or not all(
        isinstance(auth.get(key), str) and auth[key] for key in ("order_ref", "qr_start_token")
    ):
        raise SystemExit("Avy did not return a BankID order and QR token")
    order = {"order_ref": auth["order_ref"]}
    qr_path = "/v1/auth/bankid/qr/" + quote(auth["qr_start_token"], safe="")
    status_text = "Waiting for BankID..."

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.partition("?")[0]
            if path == "/qr.svg":
                try:
                    result = request("GET", qr_path)
                    payload = result.get("qr_code") if isinstance(result, dict) else None
                except ApiError:
                    payload = None
                if not payload:
                    self.send_error(502, "BankID QR unavailable")
                    return
                body = qrcode.make(payload, image_factory=SvgPathFillImage).to_string()
                content_type = "image/svg+xml"
            elif path == "/status":
                body, content_type = status_text.encode(), "text/plain; charset=utf-8"
            elif path == "/":
                body, content_type = HTML.encode(), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    with ThreadingHTTPServer(("127.0.0.1", PORT), Handler) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            print(f"Open http://127.0.0.1:{server.server_port}/ and scan the live QR with BankID.",
                  flush=True)
            print("Confirm that the BankID app shows Avy as the relying party.", flush=True)
            deadline = time.monotonic() + TIMEOUT
            while time.monotonic() < deadline:
                result = request("POST", "/v1/auth/bankid/collect", order)
                status = result.get("status") if isinstance(result, dict) else None
                if status == "complete":
                    break
                if status not in ("pending", "failed", "cancelled"):
                    raise SystemExit("Avy returned an unknown BankID status")
                new_status = f"BankID: {status} ({result.get('hint_code', '')})"
                if status != "pending":
                    raise SystemExit(new_status)
                if new_status != status_text:
                    status_text = new_status
                    print(status_text, flush=True)
                time.sleep(1)
            else:
                raise SystemExit("BankID approval timed out")
        finally:
            server.shutdown()
            worker.join()

    token = request("POST", "/v1/auth/bankid/login", order)
    if not isinstance(token, dict) or not isinstance(token.get("token"), str) or not token["token"].strip():
        raise SystemExit("Avy login did not return a usable token")
    write_private_json(TOKEN_FILE, token)
    print(f"OK. Token written to {TOKEN_FILE} (mode 0600). Never commit or share it.")
    try:
        refresh_capabilities()
        print(f"Capability map saved to {CAP_FILE}")
    except OSError as exc:
        print(f"Warning: could not save capability map: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()

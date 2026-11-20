#!/usr/bin/env python3
"""Log in to Avy with your own BankID using a live QR on localhost."""
import argparse
import os
import secrets
import sys
import threading
import time
from functools import partial
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

from avy import ApiError, CAP_FILE, TOKEN_FILE, call, refresh_capabilities, write_private_json

PORT = int(os.environ.get("AVY_LOGIN_PORT", "8765"))
TIMEOUT = int(os.environ.get("AVY_LOGIN_TIMEOUT", "300"))

HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Avy login</title><style>
body{font-family:sans-serif;text-align:center;margin:2rem}
img{width:min(360px,100%);aspect-ratio:1;image-rendering:pixelated}
</style></head><body><h2>Avy BankID login</h2>
<p>Approve only if the BankID app shows <strong>Avy</strong>.</p>
<!-- launch -->
<p>On another device, scan the live QR with the BankID app.</p>
<img id="qr" src="/qr.svg" alt="Live BankID QR code"><p id="status">Waiting...</p>
<script>
const img=document.getElementById('qr');
setInterval(()=>{img.src='/qr.svg?t='+Date.now();},1000);
setInterval(async()=>{const r=await fetch('/status');
document.getElementById('status').textContent=await r.text();},2000);
const launch = document.getElementById('bankid-launch');
if (launch) {
    const ios = /iPhone|iPad|iPod/.test(navigator.userAgent)
        || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const android = /Android/.test(navigator.userAgent);
    if ((ios || android) && !history.state?.bankidAttempted) {
        history.replaceState({bankidAttempted: true}, '');
        location.assign(launch.href);
    }
}
</script></body></html>"""

INVITE_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Private Avy login</title></head><body><h1>Private Avy login</h1>
<p id="invite-status" role="status">Open the full invite link from your terminal.
This page needs JavaScript to open it.</p>
<script>
async function redeem() {
    const status = document.getElementById('invite-status');
    const invite = location.hash.slice(1);
    if (!invite) return;
    history.replaceState(null, '', '/');
    if (!window.isSecureContext) {
        status.textContent = 'Open your invite using HTTPS.';
        return;
    }
    status.textContent = 'Opening login…';
    try {
        const reply = await fetch('/redeem', {
            method: 'POST',
            headers: {'Content-Type': 'application/octet-stream'},
            body: invite,
            redirect: 'error',
        });
        if (reply.status === 204) {
            location.reload();
            return;
        }
    } catch (_) {}
    status.textContent = 'This invite could not be opened. Restart avy-login for a new invite.';
}
window.addEventListener('hashchange', redeem);
redeem();
</script></body></html>"""

SESSION_COOKIE = "__Host-avy-login"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", action="store_true",
                        help="require a one-time invite before displaying login over an HTTPS tunnel")
    args = parser.parse_args()
    try:
        _login(remote=args.remote)
    except (ApiError, OSError) as exc:
        raise SystemExit(str(exc)) from None


def _login(*, remote=False):
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
    auto_start = auth.get("auto_start_token")
    launch = ""
    if isinstance(auto_start, str) and auto_start.strip():
        query = f"autostarttoken={quote(auto_start, safe='')}&amp;redirect=null"
        launch = (f'<p><a id="bankid-launch" rel="noreferrer" href="https://app.bankid.com/?{query}">'
                  'Open BankID</a></p>')
    login_page = HTML.replace("<!-- launch -->", launch).encode()
    status_text = "Waiting for BankID..."
    deadline = time.monotonic() + TIMEOUT
    invite = secrets.token_urlsafe(32) if remote else None
    session = None
    access_lock = threading.Lock()
    closed = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        timeout = 5 if remote else None

        def _allowed(self):
            if not remote:
                return True
            if closed.is_set() or time.monotonic() >= deadline or session is None:
                return False
            try:
                cookie = SimpleCookie(self.headers.get("Cookie", "")).get(SESSION_COOKIE)
            except CookieError:
                return False
            return cookie is not None and secrets.compare_digest(
                cookie.value.encode(), session.encode())

        def do_POST(self):
            nonlocal invite, session
            if not remote or self.path != "/redeem":
                self.send_error(404)
                return
            if (self.headers.get_all("Content-Length") != ["43"]
                    or self.headers.get("Transfer-Encoding") is not None
                    or self.headers.get("Content-Type") != "application/octet-stream"):
                self.send_error(400)
                return
            supplied = self.rfile.read(43)
            with access_lock:
                if (invite is not None and not closed.is_set() and time.monotonic() < deadline
                        and secrets.compare_digest(supplied, invite.encode())):
                    session = secrets.token_urlsafe(32)
                    invite = None
                    granted = session
                else:
                    granted = None
            if granted is None:
                self.send_error(403)
                return
            self.send_response(204)
            self.send_header("Set-Cookie",
                             f"{SESSION_COOKIE}={granted}; Secure; HttpOnly; SameSite=Strict; Path=/")
            self.end_headers()

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; "
                             "base-uri 'none'; img-src 'self'; connect-src 'self'; "
                             "script-src 'unsafe-inline'; style-src 'unsafe-inline'")
            super().end_headers()

        def do_GET(self):
            path = self.path.partition("?")[0]
            allowed = self._allowed()
            if not allowed and path != "/":
                self.send_error(403)
                return
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
                body = login_page if allowed else INVITE_PAGE.encode()
                content_type = "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            if allowed and remote and not self._allowed():
                self.send_error(403)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    with ThreadingHTTPServer(("127.0.0.1", PORT), Handler) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            if remote:
                print(f"Protected login on port {server.server_port}. Point your HTTPS tunnel at this port.",
                      flush=True)
                print(f"Invite suffix: #{invite}", flush=True)
            else:
                print(f"Open http://127.0.0.1:{server.server_port}/ and scan the live QR with BankID.",
                      flush=True)
            print("Confirm that the BankID app shows Avy as the relying party.", flush=True)
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
            with access_lock:
                closed.set()
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

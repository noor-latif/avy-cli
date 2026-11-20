#!/usr/bin/env python3
"""Log in to Avy with your own BankID using a live QR on localhost."""
import argparse
import datetime
import json
import os
import sys
import threading
import time
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

from avy import (ApiError, CAP_FILE, TOKEN_FILE, call, refresh_capabilities,
                 token_expiry, write_private_json)

PORT = int(os.environ.get("AVY_LOGIN_PORT", "8765"))
TIMEOUT = int(os.environ.get("AVY_LOGIN_TIMEOUT", "300"))
EXPIRED_HINTS = ("startFailed", "expiredTransaction")

HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Avy login</title><style>
body{font-family:sans-serif;text-align:center;margin:2rem}
img{width:min(360px,100%);aspect-ratio:1;image-rendering:pixelated}
</style></head><body><h2>Avy BankID login</h2>
<p>Approve only if the BankID app shows <strong>Avy</strong>.</p>
<p><a id="bankid-launch" rel="noreferrer" href="https://app.bankid.com/">Open BankID</a>
<a id="bankid-web" href="https://app.bankid.com/">BankID did not open?</a></p>
<p>On another device, scan the live QR with the BankID app.</p>
<img id="qr" src="/qr.svg" alt="Live BankID QR code"><p id="status">Waiting...</p>
<script>
const img=document.getElementById('qr');
img.onerror=()=>{document.getElementById('status').textContent='QR expired. Reload this page.';};
setInterval(()=>{img.src='/qr.svg?t='+Date.now();},1000);
const poll=setInterval(async()=>{const r=await fetch('/status');const t=await r.text();
document.getElementById('status').textContent=t;
if(t==='BankID: retrying'){history.replaceState({},'');location.replace('/');}
if(t.startsWith('Logged in')){clearInterval(poll);}},2000);
const launch = document.getElementById('bankid-launch');
const web = document.getElementById('bankid-web');
const agent = navigator.userAgent;
const mobile = /iPhone|iPad|iPod|Android/.test(agent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const inApp = /FBAN|FBAV|Instagram|Line\\/|WhatsApp|Slack|Twitter|Puffin|GSA\\//.test(agent)
    || (/iPhone|iPad/.test(agent) && !/Safari|CriOS|FxiOS|EdgiOS/.test(agent));
const scheme = token => 'bankid:///?autostarttoken=' + encodeURIComponent(token)
    + '&redirect=' + encodeURIComponent(mobile ? location.origin + '/#bankid' : 'null');
async function arm() {
    try {
        const info = await (await fetch('/launch')).json();
        if (info.token && info.age <= 25) return info.token;
        return (await (await fetch('/rearm', {method: 'POST'})).json()).token;
    } catch (_) { return null; }
}
if (launch) {
    const ready = arm().then(token => {
        if (!token) return null;
        const url = scheme(token);
        launch.href = url;
        web.href = url.replace('bankid:///?', 'https://app.bankid.com/?');
        return url;
    });
    if (inApp) {
        document.getElementById('status').textContent =
            'This browser cannot hand off to BankID. Open this page in Safari or Chrome first.';
    } else if (mobile && !location.hash) {
        ready.then(url => { if (url) location.assign(url); });
    }
}
</script></body></html>"""

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true",
                        help="replace a stored session that has not expired")
    args = parser.parse_args()
    try:
        _login(confirm=args.confirm)
    except (ApiError, OSError) as exc:
        raise SystemExit(str(exc)) from None


def _live_session():
    """True when the stored token is present and not provably expired."""
    try:
        token = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))["token"]
    except (OSError, KeyError, TypeError, ValueError):
        return False
    expires = token_expiry(token) if isinstance(token, str) else None
    if expires is None:
        return True
    return datetime.datetime.fromisoformat(expires) > datetime.datetime.now(datetime.timezone.utc)


def _account_label(profile):
    """Account name from the profile, for the operator reading the terminal."""
    if not isinstance(profile, dict):
        return None
    for key in ("name", "full_name", "email"):
        value = profile.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return next((value.strip() for key, value in profile.items()
                 if key.endswith("_name") and isinstance(value, str) and value.strip()), None)


def _login(*, confirm=False):
    import qrcode
    from qrcode.image.svg import SvgPathFillImage

    if _live_session() and not confirm:
        raise SystemExit(
            f"{TOKEN_FILE} holds a session that has not expired; run avy-login --confirm "
            "to replace it.")
    request = partial(call, authenticated=False)
    state = {"order": None, "qr_path": None, "token": "", "armed_at": 0.0, "generation": 0,
             "deadline": None, "text": "Waiting for BankID..."}
    state_lock = threading.Lock()

    def arm():
        """Ask Avy for an order; the app must start it within about 30 seconds.

        Only the page arms one, never a timer: the clock starts when a person has the
        page open, and a second live order would let the app approve the wrong one.
        """
        auth = request("POST", "/v1/auth/bankid/auth", {})
        if not isinstance(auth, dict) or not all(
            isinstance(auth.get(key), str) and auth[key] for key in ("order_ref", "qr_start_token")
        ):
            raise SystemExit("Avy did not return a BankID order and QR token")
        auto_start = auth.get("auto_start_token")
        with state_lock:
            state.update(order={"order_ref": auth["order_ref"]},
                         qr_path="/v1/auth/bankid/qr/" + quote(auth["qr_start_token"], safe=""),
                         token=auto_start if isinstance(auto_start, str) else "",
                         armed_at=time.monotonic(),
                         deadline=state["deadline"] or time.monotonic() + TIMEOUT,
                         generation=state["generation"] + 1)
        return state["order"]

    opened_by = time.monotonic() + TIMEOUT

    def deadline():
        """The login timeout runs from the first page load, not from process start."""
        return state["deadline"] or opened_by

    def wait_for_order(generation):
        """Block until the page arms an order, so the app and page never disagree."""
        while time.monotonic() < deadline():
            with state_lock:
                if state["generation"] != generation:
                    return True
            time.sleep(0.5)
        return False

    class Handler(BaseHTTPRequestHandler):
        timeout = 5

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
            if path == "/qr.svg":
                try:
                    if state["qr_path"] is None:
                        raise ApiError("no order armed")
                    result = request("GET", state["qr_path"])
                    payload = result.get("qr_code") if isinstance(result, dict) else None
                except ApiError:
                    payload = None
                if not payload:
                    self.send_error(502, "BankID QR unavailable")
                    return
                body = qrcode.make(payload, image_factory=SvgPathFillImage).to_string()
                content_type = "image/svg+xml"
            elif path == "/status":
                body, content_type = state["text"].encode(), "text/plain; charset=utf-8"
            elif path == "/launch":
                age = round(time.monotonic() - state["armed_at"], 1) if state["order"] else None
                body = json.dumps({"token": state["token"], "age": age}).encode()
                content_type = "application/json"
            elif path == "/":
                body, content_type = HTML.encode(), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            if self.path.partition("?")[0] != "/rearm":
                self.send_error(404)
                return
            arm()
            body = json.dumps({"token": state["token"]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
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
            print("To log in from a phone, tunnel this port and open the tunnel URL there.",
                  flush=True)
            print("The BankID order starts when the page loads.",
                  flush=True)
            print("Confirm that the BankID app shows Avy as the relying party.", flush=True)
            while time.monotonic() < deadline():
                with state_lock:
                    order, generation = state["order"], state["generation"]
                if order is None:
                    if not wait_for_order(generation):
                        raise SystemExit("BankID approval timed out")
                    continue
                result = request("POST", "/v1/auth/bankid/collect", order)
                status = result.get("status") if isinstance(result, dict) else None
                if status == "complete":
                    state["text"] = "Logged in. You can close this page."
                    time.sleep(3)
                    break
                if status not in ("pending", "failed", "cancelled"):
                    raise SystemExit("Avy returned an unknown BankID status")
                hint = result.get("hint_code", "")
                if status == "pending":
                    text = f"BankID: pending ({hint})"
                    if text != state["text"]:
                        state["text"] = text
                        print(text, flush=True)
                elif hint in EXPIRED_HINTS:
                    state["text"] = "BankID: order expired. Reload this page."
                    print(state["text"], flush=True)
                    if not wait_for_order(generation):
                        raise SystemExit("BankID approval timed out")
                    continue
                else:
                    raise SystemExit(f"BankID: {status} ({hint})")
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
        label = _account_label(call("GET", "/v1/auth/profile"))
    except ApiError:
        label = None
    print(f"Logged in as {label}." if label else "Logged in; Avy did not return an account name.")
    try:
        refresh_capabilities()
        print(f"Capability map saved to {CAP_FILE}")
    except OSError as exc:
        print(f"Warning: could not save capability map: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()

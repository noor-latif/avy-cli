import base64
import importlib.util
import io
import itertools
import json
import shutil
import tempfile
import threading
import time
import unittest
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import ExitStack, redirect_stdout
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

import avy_login


def token_expiring_in(seconds):
    """A token shaped like Avy's, so expiry is readable without the signing key."""
    payload = base64.urlsafe_b64encode(json.dumps({"exp": int(time.time()) + seconds}).encode())
    return f"header.{payload.decode().rstrip('=')}.signature"


class SyntheticAvy:
    """Answer BankID calls without touching Avy, replaying a scripted collect sequence."""

    def __init__(self, done, frames, collect):
        self.done = done
        self.frames = frames
        self.collect = iter(collect)
        self.last = collect[-1]
        self.orders = 0
        self.collecting = threading.Event()

    def __call__(self, method, path, body=None, *, authenticated=True):
        if path.startswith("/v1/auth/bankid/") and authenticated:
            raise AssertionError(f"BankID call must not be authenticated: {path}")
        if path == "/v1/auth/bankid/auth":
            self.orders += 1
            return {"order_ref": f"fixture-order-{self.orders}", "qr_start_token": "fixture-qr",
                    "auto_start_token": "synthetic-launch&value"}
        if path == "/v1/auth/bankid/qr/fixture-qr":
            return {"qr_code": next(self.frames)}
        if path == "/v1/auth/bankid/collect":
            self.collecting.set()
            status, hint = next(self.collect, self.last)
            if status == "cancelled":
                self.done.wait(5)
            return {"status": status, "hint_code": hint}
        if path == "/v1/auth/bankid/login":
            return {"token": "synthetic-token"}
        if authenticated and path == "/v1/auth/profile":
            return {"name": "Synthetic Person"}
        raise AssertionError(f"Unexpected request: {method} {path}")


@unittest.skipUnless(importlib.util.find_spec("qrcode"), "login dependency not installed")
class LoginServerTestCase(unittest.TestCase):
    def start(self, *, collect=(("cancelled", ""),), token=None, confirm=False):
        """Run _login on a real loopback server bound to an ephemeral port."""
        self.done = threading.Event()
        self.port = Future()
        self.frames = (f"synthetic frame {n}" for n in itertools.count(1))
        self.output = io.StringIO()
        self.tokens = Path(tempfile.mkdtemp(prefix="avy-login-test-"))
        self.addCleanup(shutil.rmtree, self.tokens)
        self.token_file = self.tokens / "token.json"
        if token is not None:
            self.token_file.write_text(json.dumps({"token": token}), encoding="utf-8")

        def bind(_, handler):
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            self.port.set_result(server.server_port)
            return server

        stack = ExitStack()
        self.addCleanup(stack.close)
        self.avy = SyntheticAvy(self.done, self.frames, collect)
        stack.enter_context(patch.object(avy_login, "call", self.avy))
        stack.enter_context(patch.object(avy_login, "TOKEN_FILE", self.token_file))
        stack.enter_context(patch.object(avy_login, "CAP_FILE", self.tokens / "capabilities.json"))
        stack.enter_context(patch.object(avy_login, "refresh_capabilities", lambda: None))
        stack.enter_context(patch.object(avy_login, "ThreadingHTTPServer", bind))
        stack.enter_context(redirect_stdout(self.output))
        pool = stack.enter_context(ThreadPoolExecutor())
        self.login = pool.submit(avy_login._login, confirm=confirm)
        self.addCleanup(self.finish)
        return self.port.result(timeout=5)

    def finish(self):
        self.done.set()
        try:
            self.login.result(timeout=5)
        except SystemExit as exc:
            self.assertIn("cancelled", str(exc))

    def complete(self):
        """Let collect finish with status=complete and wait for the token to be written."""
        self.done.set()
        self.login.result(timeout=5)

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.port.result(timeout=5), timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.getheaders(), response.read()
        finally:
            connection.close()

    @staticmethod
    def header(headers, name):
        return next((value for key, value in headers if key.lower() == name.lower()), None)

    @staticmethod
    def refuse_to_call(*_, **__):
        raise AssertionError("login must stop before calling Avy")


class LoginTests(LoginServerTestCase):
    def test_page_serves_qr_status_and_launch_link(self):
        self.start()
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(self.header(headers, "Content-Type"), "text/html; charset=utf-8")
        self.assertEqual(self.header(headers, "Cache-Control"), "no-store")
        self.assertIn(b'src="/qr.svg"', body)
        self.assertIn(b'id="bankid-launch"', body)
        self.assertNotIn(b"synthetic-launch", body)

        status, headers, body = self.request("POST", "/rearm")
        self.assertEqual(status, 200)
        self.assertEqual(self.header(headers, "Content-Type"), "application/json")
        self.assertEqual(json.loads(body)["token"], "synthetic-launch&value")
        self.assertEqual(self.avy.orders, 2, "a launch re-arms before opening BankID")

        images = []
        for tick in (1, 2):
            status, headers, body = self.request("GET", f"/qr.svg?t={tick}")
            self.assertEqual(status, 200)
            self.assertEqual(self.header(headers, "Content-Type"), "image/svg+xml")
            self.assertEqual(self.header(headers, "Cache-Control"), "no-store")
            self.assertEqual(
                ElementTree.fromstring(body).tag, "{http://www.w3.org/2000/svg}svg")
            images.append(body)
        self.assertNotEqual(*images)

        status, headers, body = self.request("GET", "/status")
        self.assertEqual(status, 200)
        self.assertEqual(self.header(headers, "Content-Type"), "text/plain; charset=utf-8")
        self.assertIn(b"BankID", body)

    def test_unexpired_session_needs_confirm(self):
        tokens = Path(tempfile.mkdtemp(prefix="avy-login-test-"))
        self.addCleanup(shutil.rmtree, tokens)
        token_file = tokens / "token.json"
        stored = token_expiring_in(3600)
        token_file.write_text(json.dumps({"token": stored}), encoding="utf-8")
        with patch.object(avy_login, "TOKEN_FILE", token_file), \
                patch.object(avy_login, "call", self.refuse_to_call), \
                self.assertRaises(SystemExit) as raised:
            avy_login._login()
        self.assertIn("--confirm", str(raised.exception))
        self.assertEqual(json.loads(token_file.read_text(encoding="utf-8"))["token"], stored)

    def test_expired_session_is_replaced_without_confirm(self):
        self.start(collect=(("complete", ""),), token=token_expiring_in(-60))
        self.complete()
        self.assertEqual(
            json.loads(self.token_file.read_text(encoding="utf-8"))["token"], "synthetic-token")
        self.assertIn("Logged in as Synthetic Person.", self.output.getvalue())

    def test_confirm_replaces_an_unexpired_session(self):
        self.start(collect=(("complete", ""),), token=token_expiring_in(3600), confirm=True)
        self.complete()
        self.assertEqual(
            json.loads(self.token_file.read_text(encoding="utf-8"))["token"], "synthetic-token")

    def test_expired_order_is_replaced_and_login_completes(self):
        self.start(collect=(("failed", "startFailed"), ("complete", "")))
        self.complete()
        self.assertEqual(self.avy.orders, 2)
        self.assertIn("new order 1/5", self.output.getvalue())
        self.assertEqual(
            json.loads(self.token_file.read_text(encoding="utf-8"))["token"], "synthetic-token")
import importlib.util
import io
import itertools
import re
import threading
import time
import unittest
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import ExitStack, redirect_stdout
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch
from xml.etree import ElementTree

import avy_login

COOKIE = "__Host-avy-login"
INVITE = re.compile(r"Invite suffix: #(\S+)")


class SyntheticAvy:
    """Answer BankID calls without touching Avy, and hold collect until the test ends."""

    def __init__(self, done, frames):
        self.done = done
        self.frames = frames
        self.collecting = threading.Event()

    def __call__(self, method, path, body=None, *, authenticated):
        if authenticated:
            raise AssertionError("login must not authenticate the BankID calls")
        if path == "/v1/auth/bankid/auth":
            return {"order_ref": "fixture-order", "qr_start_token": "fixture-qr"}
        if path == "/v1/auth/bankid/collect":
            self.collecting.set()
            self.done.wait(5)
            return {"status": "cancelled"}
        if path == "/v1/auth/bankid/qr/fixture-qr":
            return {"qr_code": next(self.frames)}
        raise AssertionError(f"Unexpected request: {method} {path}")


@unittest.skipUnless(importlib.util.find_spec("qrcode"), "login dependency not installed")
class LoginServerTestCase(unittest.TestCase):
    def start(self, *, remote=True):
        """Run _login on a real loopback server bound to an ephemeral port."""
        self.done = threading.Event()
        self.port = Future()
        self.frames = (f"synthetic frame {n}" for n in itertools.count(1))
        self.output = io.StringIO()

        def bind(_, handler):
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            self.port.set_result(server.server_port)
            return server

        stack = ExitStack()
        self.addCleanup(stack.close)
        self.avy = SyntheticAvy(self.done, self.frames)
        stack.enter_context(patch.object(avy_login, "call", self.avy))
        stack.enter_context(patch.object(avy_login, "ThreadingHTTPServer", bind))
        stack.enter_context(redirect_stdout(self.output))
        pool = stack.enter_context(ThreadPoolExecutor())
        self.login = pool.submit(avy_login._login, remote=remote)
        self.addCleanup(self.finish)
        return self.port.result(timeout=5)

    def finish(self):
        self.done.set()
        try:
            self.login.result(timeout=5)
        except SystemExit as exc:
            self.assertIn("cancelled", str(exc))
        else:
            self.fail("_login did not stop after BankID was cancelled")

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

    def redeem(self, token, content_type="application/octet-stream"):
        if isinstance(token, str):
            token = token.encode()
        headers = {} if content_type is None else {"Content-Type": content_type}
        return self.request("POST", "/redeem", body=token, headers=headers)

    def redeem_declared(self, length, content_type="application/octet-stream"):
        """Declare a length or type the server must reject before reading a body."""
        headers = {"Content-Length": str(length)}
        if content_type is not None:
            headers["Content-Type"] = content_type
        return self.request("POST", "/redeem", headers=headers)

    def cookie(self, headers):
        values = [value for key, value in headers if key.lower() == "set-cookie"]
        self.assertEqual(len(values), 1, values)
        jar = SimpleCookie()
        jar.load(values[0])
        self.assertIn(COOKIE, jar)
        return values[0], jar[COOKIE]

    def invite(self, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            match = INVITE.search(self.output.getvalue())
            if match:
                return match.group(1)
            time.sleep(0.02)
        self.fail(f"no invite was printed: {self.output.getvalue()!r}")

    def assert_no_cookie(self, headers):
        self.assertIsNone(self.header(headers, "Set-Cookie"))


class RemoteLoginTests(LoginServerTestCase):
    def test_public_bootstrap_has_no_qr_or_credentials(self):
        self.start(remote=True)
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(self.header(headers, "Content-Type"), "text/html; charset=utf-8")
        self.assertEqual(self.header(headers, "Cache-Control"), "no-store")
        self.assertNotIn(b"/qr.svg", body)
        self.assertNotIn(b"<img", body)
        self.assertNotIn(b"fixture-qr", body)
        invite = self.invite()
        self.assertNotIn(invite.encode(), body)

        for path in ("/qr.svg", "/status"):
            status, headers, body = self.request("GET", path)
            self.assertEqual(status, 403, path)
            self.assert_no_cookie(headers)
        status, _, _ = self.request(
            "GET", "/qr.svg", headers={"Cookie": f"{COOKIE}={'x' * 43}"})
        self.assertEqual(status, 403)

    def test_redeem_sets_host_cookie_and_unlocks_qr(self):
        self.start(remote=True)
        token = self.invite()
        self.assertRegex(token, r"\A[A-Za-z0-9_-]{43}\Z")

        status, headers, body = self.redeem(token)
        self.assertEqual(status, 204)
        self.assertEqual(body, b"")
        self.assertEqual(self.header(headers, "Cache-Control"), "no-store")
        _, morsel = self.cookie(headers)
        self.assertRegex(morsel.value, r"\A[A-Za-z0-9_-]{43}\Z")
        self.assertIs(morsel["secure"], True)
        self.assertIn("httponly", morsel)
        self.assertEqual(morsel["samesite"], "Strict")
        self.assertEqual(morsel["path"], "/")
        self.assertEqual(morsel["domain"], "")

        cookie = {"Cookie": f"{COOKIE}={morsel.value}"}
        status, headers, body = self.request("GET", "/", headers=cookie)
        self.assertEqual(status, 200)
        self.assertIn(b'src="/qr.svg"', body)
        self.assertNotIn(b"Open the full invite link", body)

        status, headers, body = self.request("GET", "/qr.svg", headers=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(self.header(headers, "Content-Type"), "image/svg+xml")
        self.assertEqual(self.header(headers, "Cache-Control"), "no-store")
        self.assertEqual(ElementTree.fromstring(body).tag, "{http://www.w3.org/2000/svg}svg")

        status, headers, body = self.request("GET", "/status", headers=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(self.header(headers, "Content-Type"), "text/plain; charset=utf-8")
        self.assertIn(b"BankID", body)

    def test_redeem_rejects_bad_malformed_and_replayed_tokens(self):
        self.start(remote=True)
        token = self.invite()
        bad = "A" * 43
        if bad == token:
            bad = "B" * 43
        status, headers, _ = self.redeem(bad)
        self.assertEqual(status, 403)
        self.assert_no_cookie(headers)

        for length, content_type in ((42, "application/octet-stream"),
                                     (44, "application/octet-stream"),
                                     (43, "text/plain"),
                                     (43, None)):
            status, headers, _ = self.redeem_declared(length, content_type)
            self.assertEqual(status, 400, (length, content_type))
            self.assert_no_cookie(headers)

        status, headers, _ = self.redeem(token)
        self.assertEqual(status, 204)
        _, morsel = self.cookie(headers)

        status, headers, _ = self.redeem(token)
        self.assertEqual(status, 403)
        self.assert_no_cookie(headers)

        status, _, _ = self.request(
            "GET", "/status", headers={"Cookie": f"{COOKIE}={morsel.value}"})
        self.assertEqual(status, 200)

    def test_deadline_revokes_browser_session(self):
        clock = SimpleNamespace(now=100)
        patch_clock = patch.object(avy_login, "time", SimpleNamespace(monotonic=lambda: clock.now))
        patch_clock.start()
        self.addCleanup(patch_clock.stop)
        self.start()
        status, headers, _ = self.redeem(self.invite())
        self.assertEqual(status, 204)
        _, morsel = self.cookie(headers)
        cookie = {"Cookie": f"{COOKIE}={morsel.value}"}
        self.assertTrue(self.avy.collecting.wait(5))
        clock.now += avy_login.TIMEOUT
        for path in ("/qr.svg", "/status"):
            self.assertEqual(self.request("GET", path, headers=cookie)[0], 403)

    def test_redeem_is_single_use_under_concurrency(self):
        self.start(remote=True)
        token = self.invite().encode()
        barrier = threading.Barrier(2)

        def attempt(_):
            connection = HTTPConnection(
                "127.0.0.1", self.port.result(timeout=5), timeout=5)
            try:
                barrier.wait(5)
                connection.request(
                    "POST", "/redeem", body=token,
                    headers={"Content-Type": "application/octet-stream"})
                response = connection.getresponse()
                headers = response.getheaders()
                response.read()
                return response.status, headers
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        self.assertEqual(sorted(status for status, _ in results), [204, 403])
        granted = sum(
            1 for _, headers in results if self.header(headers, "Set-Cookie"))
        self.assertEqual(granted, 1)


class LocalLoginTests(LoginServerTestCase):
    def test_local_mode_serves_fresh_svgs_without_an_invite(self):
        self.start(remote=False)
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b'src="/qr.svg"', body)

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
        self.assertNotIn("Invite suffix", self.output.getvalue())
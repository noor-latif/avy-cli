import importlib.util
import unittest
from concurrent.futures import Future, ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from threading import Event
from unittest.mock import patch
from urllib.request import urlopen
from xml.etree import ElementTree

import avy_login


@unittest.skipUnless(importlib.util.find_spec("qrcode"), "login dependency not installed")
class LoginPageTests(unittest.TestCase):
    def test_qr_route_serves_fresh_svgs(self):
        address, done = Future(), Event()
        frames = iter(("first synthetic frame", "second synthetic frame"))

        def request(method, path, body=None, *, authenticated):
            if path.endswith("/auth"):
                return {"order_ref": "fixture-order", "qr_start_token": "fixture-qr"}
            if path.endswith("/collect"):
                done.wait(5)
                return {"status": "cancelled"}
            if path.endswith("/qr/fixture-qr"):
                return {"qr_code": next(frames)}
            raise AssertionError(f"Unexpected request: {method} {path}")

        def bind(_, handler):
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            address.set_result(f"http://127.0.0.1:{server.server_port}")
            return server

        with patch.object(avy_login, "call", request), patch.object(avy_login, "ThreadingHTTPServer", bind), \
                patch("builtins.print"), ThreadPoolExecutor() as pool:
            login = pool.submit(avy_login._login)
            try:
                base = address.result(timeout=5)
                with urlopen(base, timeout=5) as page:
                    self.assertIn(b'src="/qr.svg"', page.read())
                images = []
                for tick in (1, 2):
                    with urlopen(f"{base}/qr.svg?t={tick}", timeout=5) as image:
                        self.assertEqual(image.headers.get_content_type(), "image/svg+xml")
                        self.assertEqual(image.headers["Cache-Control"], "no-store")
                        body = image.read()
                        self.assertEqual(ElementTree.fromstring(body).tag, "{http://www.w3.org/2000/svg}svg")
                        images.append(body)
                self.assertNotEqual(*images)
            finally:
                done.set()
            with self.assertRaisesRegex(SystemExit, "cancelled"):
                login.result(timeout=5)

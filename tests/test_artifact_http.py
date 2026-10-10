from __future__ import annotations

import email.message
import importlib.util
import os
import pathlib
import socket
import ssl
import sys
import threading
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("artifact_http", ROOT / "scripts/artifact_http.py")
assert SPEC and SPEC.loader
HTTP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HTTP)


class Response:
    def __init__(self, status: int = 200, headers: list[tuple[str, str]] | None = None, body: bytes = b"chart"):
        self.status = status
        self.headers = email.message.Message()
        for key, value in headers or [("Content-Length", str(len(body)))]:
            self.headers[key] = value
        self.body = body
        self.closed = False

    def read(self, maximum: int) -> bytes:
        return self.body[:maximum]

    def close(self) -> None:
        self.closed = True


class Connection:
    def __init__(self, response: Response):
        self.response = response
        self.transport_socket = None
        self.closed = False

    def request(self, *args: object, **kwargs: object) -> None:
        pass

    def getresponse(self) -> Response:
        return self.response

    def close(self) -> None:
        self.closed = True


class ArtifactHTTPTest(unittest.TestCase):
    def test_destination_syntax_and_transient_signature_contract(self) -> None:
        for url in ["http://public.invalid/chart", "https://user:password@public.invalid/chart",
                    "https://public.invalid/chart#fragment", "https://public.invalid:0/chart",
                    "https://public.invalid/chart?token=fixture", "https://public.invalid/chart\r\n"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                HTTP.destination(url, transient_signature=False)
        self.assertEqual(HTTP.destination("https://public.invalid/chart?token=fixture", transient_signature=True).hostname, "public.invalid")
        with self.assertRaises(ValueError):
            HTTP.destination("https://user:password@public.invalid/chart", transient_signature=True)

    def test_all_dns_answers_validate_before_any_contact(self) -> None:
        answers = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (value, 443))
                   for value in ("8.8.8.8", "127.0.0.1")]
        with mock.patch.object(socket, "getaddrinfo", return_value=answers), mock.patch.object(HTTP, "PinnedHTTPSConnection") as connection:
            with self.assertRaisesRegex(ValueError, "non-public"):
                HTTP.fetch_public_https("https://public.invalid/chart", 1024)
            connection.assert_not_called()

    def test_dns_timeout_joins_only_its_owned_child(self) -> None:
        children: list[int] = []
        fork = os.fork

        def recorded_fork() -> int:
            child = fork()
            if child:
                children.append(child)
            return child

        def stalled_dns(*args: object, **kwargs: object) -> None:
            time.sleep(30)

        with mock.patch.object(os, "fork", side_effect=recorded_fork), mock.patch.object(socket, "getaddrinfo", side_effect=stalled_dns), mock.patch.object(HTTP, "DNS_SECONDS", 0.05):
            started = time.monotonic()
            with self.assertRaises(ValueError):
                HTTP.public_addresses("public.invalid", 443, started + 1)
            self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(len(children), 1)
        with self.assertRaises(ChildProcessError):
            os.waitpid(children[0], os.WNOHANG)

    def test_numeric_connect_keeps_original_tls_host_without_dns(self) -> None:
        connection = mock.Mock()
        context = mock.Mock(check_hostname=True, verify_mode=ssl.CERT_REQUIRED, post_handshake_auth=False)
        context.wrap_socket.return_value = connection
        with mock.patch.object(ssl, "_create_default_https_context", return_value=context), mock.patch.object(socket, "socket", return_value=connection), mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("unexpected connection DNS")):
            client = HTTP.PinnedHTTPSConnection("public.invalid", 443, [(socket.AF_INET, "8.8.8.8")], time.monotonic() + 1)
            try:
                client.connect()
                connection.connect.assert_called_once_with(("8.8.8.8", 443))
                context.wrap_socket.assert_called_once_with(connection, server_hostname="public.invalid")
            finally:
                client.close()

    def test_unverified_tls_context_is_rejected_before_connect(self) -> None:
        for checks, verification in [(False, ssl.CERT_REQUIRED), (False, ssl.CERT_NONE)]:
            context = mock.Mock(check_hostname=checks, verify_mode=verification, post_handshake_auth=False)
            with self.subTest(checks=checks, verification=verification), mock.patch.object(ssl, "_create_default_https_context", return_value=context), mock.patch.object(socket, "socket") as connection:
                with self.assertRaisesRegex(ValueError, "TLS verification"):
                    HTTP.PinnedHTTPSConnection("public.invalid", 443, [(socket.AF_INET, "8.8.8.8")], time.monotonic() + 1)
                connection.assert_not_called()

    def test_redirect_budget_and_response_framing_fail_closed(self) -> None:
        cases = [Response(302, [("Location", "/again")]), Response(200, [("Content-Length", "5"), ("Content-Length", "5")]),
                 Response(200, [("Content-Length", "5"), ("Transfer-Encoding", "chunked")]),
                 Response(200, [("Content-Length", "-1")]), Response(200, [("Content-Length", "6")]),
                 Response(200, [("Content-Encoding", "gzip")]), Response(200, [("Content-Length", "1025")])]
        for response in cases:
            clients: list[Connection] = []

            def factory(*args: object) -> Connection:
                client = Connection(response)
                clients.append(client)
                return client

            with self.subTest(headers=str(response.headers)), mock.patch.object(HTTP, "public_addresses", return_value=[(socket.AF_INET, "8.8.8.8")]), mock.patch.object(HTTP, "PinnedHTTPSConnection", side_effect=factory):
                with self.assertRaises(ValueError):
                    HTTP.fetch_public_https("https://public.invalid/chart", 1024)
            self.assertTrue(clients)
            self.assertTrue(all(client.closed for client in clients))
            self.assertTrue(response.closed)
            self.assertLessEqual(len(clients), 5)

    def test_response_deadline_owner_joins_after_abort(self) -> None:
        released = threading.Event()
        response = Response()
        connection = Connection(response)
        active = mock.Mock()
        active.shutdown.side_effect = lambda *_: released.set()
        connection.transport_socket = active

        def wait_for_abort(maximum: int) -> bytes:
            self.assertTrue(released.wait(1), "deadline did not abort its owned socket")
            return b""

        response.read = wait_for_abort
        with mock.patch.object(HTTP, "public_addresses", return_value=[(socket.AF_INET, "8.8.8.8")]), mock.patch.object(HTTP, "PinnedHTTPSConnection", return_value=connection), mock.patch.object(HTTP, "REQUEST_SECONDS", 0.05):
            with self.assertRaisesRegex(ValueError, "deadline"):
                HTTP.fetch_public_https("https://public.invalid/chart", 1024)
        self.assertTrue(response.closed and connection.closed)
        self.assertFalse(any(owner.name == "artifact-response-deadline" for owner in threading.enumerate()))

    def test_successful_body_and_deadline_owner_close(self) -> None:
        response = Response()
        connection = Connection(response)
        with mock.patch.object(HTTP, "public_addresses", return_value=[(socket.AF_INET, "8.8.8.8")]), mock.patch.object(HTTP, "PinnedHTTPSConnection", return_value=connection):
            self.assertEqual(HTTP.fetch_public_https("https://public.invalid/chart", 1024), (b"chart", "https://public.invalid/chart"))
        self.assertTrue(response.closed and connection.closed)
        self.assertFalse(any(owner.name == "artifact-response-deadline" for owner in threading.enumerate()))


if __name__ == "__main__":
    unittest.main()

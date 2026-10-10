from __future__ import annotations

import importlib.util
import io
import os
import pathlib
import socket
import ssl
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("resolve_artifacts", ROOT / "scripts/resolve_artifacts.py")
assert SPEC and SPEC.loader
RESOLVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESOLVE)


class RecordedSocket:
    def __init__(self, owner: ArtifactTransportBoundaryTest, *args: object, **kwargs: object) -> None:
        self.owner = owner
        self.request = b""

    def settimeout(self, timeout: float | None) -> None:
        pass

    def setsockopt(self, *args: object) -> None:
        pass

    def connect(self, address: tuple) -> None:
        self.owner.contacts.append(address[0])

    def sendall(self, data: bytes) -> None:
        self.request += data

    def makefile(self, mode: str) -> io.BytesIO:
        if self.owner.redirect and b"Host: source.invalid\r\n" in self.request:
            return io.BytesIO(b"HTTP/1.1 302 Found\r\nLocation: https://private.invalid/chart.tgz\r\nContent-Length: 0\r\n\r\n")
        return io.BytesIO(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nchart")

    def close(self) -> None:
        pass


class FixtureTLSContext:
    # A deterministic transport double, not certificate or TLS qualification.
    check_hostname = True
    verify_mode = ssl.CERT_REQUIRED
    post_handshake_auth = False

    def set_alpn_protocols(self, protocols: list[str]) -> None:
        pass

    def wrap_socket(self, connection: RecordedSocket, *, server_hostname: str, **kwargs: object) -> RecordedSocket:
        return connection


class ArtifactTransportBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contacts: list[str] = []
        self.lookups = 0
        self.redirect = False
        self.rebind = False
        self.addCleanup(mock.patch.stopall)
        # Exercise the real urllib redirect/client path, while all transport and
        # DNS remain owned deterministic doubles. No real network is contacted.
        mock.patch.dict(os.environ, {}, clear=True).start()
        mock.patch.object(socket, "getaddrinfo", side_effect=self.addresses).start()
        mock.patch.object(socket, "socket", side_effect=lambda *args, **kwargs: RecordedSocket(self, *args, **kwargs)).start()
        mock.patch.object(ssl, "_create_default_https_context", return_value=FixtureTLSContext()).start()

    def addresses(self, host: str, port: int, *args: object, **kwargs: object) -> list[tuple]:
        if host == "source.invalid":
            self.lookups += 1
            address = "127.0.0.1" if self.rebind and self.lookups > 1 else "8.8.8.8"
        else:
            address = "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port))]

    def fetch(self) -> None:
        try:
            RESOLVE.fetch("https://source.invalid/chart.tgz", 1024)
        except ValueError:
            # Policy may reject the response after contact; the assertion below
            # specifically requires rejection before a private connect attempt.
            pass
        self.assertTrue(self.contacts, "fixture did not reach a transport attempt")

    def test_redirect_destination_is_rejected_before_contact(self) -> None:
        self.redirect = True
        self.fetch()
        self.assertNotIn("127.0.0.1", self.contacts, "private redirect was contacted before policy validation")

    def test_connection_uses_the_exact_validated_dns_addresses(self) -> None:
        self.rebind = True
        self.fetch()
        self.assertNotIn("127.0.0.1", self.contacts, "independent connection DNS selected an unvalidated address")


if __name__ == "__main__":
    unittest.main()

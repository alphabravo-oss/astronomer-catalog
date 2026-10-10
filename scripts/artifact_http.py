"""Direct public HTTPS artifact transport with pinned addresses and finite ownership."""
from __future__ import annotations

import http.client
import ipaddress
import json
import os
import select
import signal
import socket
import ssl
import threading
import time
import urllib.parse

MAX_URL_BYTES = 8192
MAX_ADDRESSES = 64
MAX_DNS_BYTES = 16 * 1024
MAX_BODY_BYTES = 256 * 1024 * 1024
REQUEST_SECONDS = 45.0
DNS_SECONDS = 5.0
MAX_REDIRECTS = 4
SENSITIVE_KEYS = frozenset({
    "access_token", "authorization", "credential", "jwt", "key", "password",
    "sig", "signature", "token", "x-amz-credential", "x-amz-signature",
})


def remaining(deadline: float) -> float:
    value = deadline - time.monotonic()
    if value <= 0:
        raise ValueError("artifact request deadline exceeded")
    return value


def destination(url: str, *, transient_signature: bool) -> urllib.parse.SplitResult:
    try:
        if not isinstance(url, str) or len(url.encode("utf-8")) > MAX_URL_BYTES:
            raise ValueError
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.fragment
                or any(ord(character) < 32 or ord(character) == 127 for character in url)
                or (parsed.port is not None and not 1 <= parsed.port <= 65535)):
            raise ValueError
        if not transient_signature and {
            key.lower() for key, _ in urllib.parse.parse_qsl(parsed.query)
        } & SENSITIVE_KEYS:
            raise ValueError
        return parsed
    except (ValueError, UnicodeError):
        raise ValueError("artifact destination must be credential-free HTTPS") from None


def public_addresses(host: str, port: int, deadline: float) -> list[tuple[int, str]]:
    """Hold the DNS child's PID through pidfd signaling and bounded final wait."""
    if (not hasattr(os, "fork") or not hasattr(os, "pidfd_open")
            or not hasattr(signal, "pidfd_send_signal")
            or signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL
            or threading.active_count() != 1):
        raise ValueError("artifact DNS requires the supported single-threaded Linux runner")
    read_fd, write_fd = os.pipe()
    try:
        child = os.fork()
    except OSError:
        os.close(read_fd)
        os.close(write_fd)
        raise ValueError("artifact DNS worker could not start") from None
    if child == 0:
        os.close(read_fd)
        try:
            records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            if not 0 < len(records) <= MAX_ADDRESSES:
                raise ValueError
            addresses = []
            for family, kind, protocol, _, address in records:
                if (family not in (socket.AF_INET, socket.AF_INET6)
                        or kind != socket.SOCK_STREAM or protocol not in (0, socket.IPPROTO_TCP)
                        or (family == socket.AF_INET6 and address[3] != 0)):
                    raise ValueError
                addresses.append([family, address[0]])
            payload = json.dumps(addresses).encode("ascii")
            if len(payload) > MAX_DNS_BYTES:
                raise ValueError
        except BaseException:
            payload = b"null"
        try:
            while payload:
                payload = payload[os.write(write_fd, payload):]
        finally:
            os.close(write_fd)
            os._exit(0)
    os.close(write_fd)
    pid_fd = None
    reaped = False
    try:
        # The unreaped child remains owned even if it exits before pidfd_open.
        pid_fd = os.pidfd_open(child)
        dns_deadline = min(deadline, time.monotonic() + DNS_SECONDS)
        payload = bytearray()
        while True:
            readable, _, _ = select.select([read_fd], [], [], remaining(dns_deadline))
            if not readable:
                raise ValueError("artifact DNS deadline exceeded")
            chunk = os.read(read_fd, min(4096, MAX_DNS_BYTES + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > MAX_DNS_BYTES:
                raise ValueError("artifact DNS response exceeds its bound")
        rows = json.loads(payload)
        if not isinstance(rows, list) or not 0 < len(rows) <= MAX_ADDRESSES:
            raise ValueError("artifact DNS resolution failed")
        addresses = []
        for row in rows:
            if (not isinstance(row, list) or len(row) != 2 or type(row[0]) is not int
                    or row[0] not in (socket.AF_INET, socket.AF_INET6)
                    or not isinstance(row[1], str)):
                raise ValueError("artifact DNS response is invalid")
            try:
                address = ipaddress.ip_address(row[1])
            except ValueError:
                raise ValueError("artifact DNS response is invalid") from None
            if not address.is_global or address.version != (4 if row[0] == socket.AF_INET else 6):
                raise ValueError("artifact destination resolves to a non-public address")
            candidate = (row[0], str(address))
            if candidate not in addresses:
                addresses.append(candidate)
        return addresses
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("artifact DNS resolution failed") from None
    finally:
        os.close(read_fd)
        # No wait/poll before signaling: the child identity remains unreaped.
        try:
            if pid_fd is not None:
                try:
                    signal.pidfd_send_signal(pid_fd, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                # pidfd_open failed while our untouched child remains unreaped.
                os.kill(child, signal.SIGKILL)
            join_deadline = time.monotonic() + 1.0
            while time.monotonic() < join_deadline:
                observed, _ = os.waitpid(child, os.WNOHANG)
                if observed == child:
                    reaped = True
                    break
                time.sleep(0.01)
            if not reaped:
                raise ValueError("artifact DNS child did not join")
        finally:
            if pid_fd is not None:
                os.close(pid_fd)


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, addresses: list[tuple[int, str]], deadline: float):
        # Canonical HTTPSConnection context verifies both the certificate and host.
        super().__init__(host, port, timeout=remaining(deadline), max_response_headers=32)
        if not self._context.check_hostname or self._context.verify_mode != ssl.CERT_REQUIRED:
            raise ValueError("artifact TLS verification is required")
        self.addresses = addresses
        self.deadline = deadline
        self.transport_socket: socket.socket | None = None

    def connect(self) -> None:
        for family, address in self.addresses:
            connection = socket.socket(family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
            self.transport_socket = connection
            try:
                connection.settimeout(remaining(self.deadline))
                target = (address, self.port) if family == socket.AF_INET else (address, self.port, 0, 0)
                connection.connect(target)
                connection.settimeout(remaining(self.deadline))
                self.sock = self._context.wrap_socket(connection, server_hostname=self.host)
                self.transport_socket = self.sock
                return
            except (OSError, TimeoutError):
                connection.close()
        raise ValueError("artifact HTTPS connection failed")


def fetch_public_https(url: str, maximum: int) -> tuple[bytes, str]:
    if type(maximum) is not int or not 0 < maximum <= MAX_BODY_BYTES:
        raise ValueError("artifact response limit is invalid")
    deadline = time.monotonic() + REQUEST_SECONDS
    current = url
    for hop in range(MAX_REDIRECTS + 1):
        parsed = destination(current, transient_signature=hop != 0)
        port = parsed.port or 443
        host = parsed.hostname
        assert host is not None
        addresses = public_addresses(host, port, deadline)
        connection = PinnedHTTPSConnection(host, port, addresses, deadline)
        stopped = threading.Event()
        expired = threading.Event()

        def expire(stopped: threading.Event, expired: threading.Event,
                   connection: PinnedHTTPSConnection) -> None:
            if not stopped.wait(max(0.0, deadline - time.monotonic())):
                expired.set()
                active = connection.transport_socket
                if active is not None:
                    try:
                        active.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    active.close()

        owner = threading.Thread(target=expire, args=(stopped, expired, connection),
                                 name="artifact-response-deadline")
        owner.start()
        response = None
        try:
            target = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
            connection.request("GET", target, headers={
                "User-Agent": "astronomer-catalog-builder/1", "Accept-Encoding": "identity",
            })
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                locations = response.headers.get_all("Location", [])
                if len(locations) != 1 or hop == MAX_REDIRECTS:
                    raise ValueError("artifact redirect limit or location is invalid")
                current = urllib.parse.urljoin(current, locations[0])
                # Next iteration validates every redirect before any connection.
                continue
            if response.status != 200:
                raise ValueError("artifact HTTPS response failed")
            lengths = response.headers.get_all("Content-Length", [])
            encodings = response.headers.get_all("Content-Encoding", [])
            transfers = response.headers.get_all("Transfer-Encoding", [])
            if (len(lengths) > 1 or len(encodings) > 1 or len(transfers) > 1
                    or (lengths and transfers) or (encodings and encodings[0].lower() != "identity")
                    or (transfers and transfers[0].lower() != "chunked")):
                raise ValueError("artifact response framing is invalid")
            if lengths and (not lengths[0].isascii() or not lengths[0].isdigit()
                            or len(lengths[0]) > 20 or int(lengths[0]) > maximum):
                raise ValueError("artifact exceeds its response bound")
            content = response.read(maximum + 1)
            if expired.is_set():
                raise ValueError("artifact request deadline exceeded")
            if len(content) > maximum:
                raise ValueError("artifact exceeds its response bound")
            if lengths and len(content) != int(lengths[0]):
                raise ValueError("artifact response body is incomplete")
            remaining(deadline)
            return content, current
        except (OSError, http.client.HTTPException, UnicodeError):
            raise ValueError("artifact HTTPS request failed") from None
        finally:
            stopped.set()
            if response is not None:
                response.close()
            connection.close()
            owner.join(timeout=1.0)
            if owner.is_alive():
                raise ValueError("artifact response deadline owner did not join")
    raise ValueError("artifact redirect limit exceeded")

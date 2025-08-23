from typing import Tuple, Optional, List, Dict
import socket as _socket
import threading
import selectors
import time
import json
import sys

VERSION = "NetSplit-1"

# Protocol error payloads sent to clients when the proxy fails early.
PROTOCOL_ERRORS: Dict[str, bytes] = {
    "no_support": b"E\x00",
    "client_error": b"E\x01",
    "proxy_error": b"E\x02",
    "invalid_server": b"E\x03",
}

class socket(_socket.socket):
    """Small _socket subclass that contains proxy helper methods.

    Intentionally lightweight: it mainly centralizes protocol error
    replies and implements helpers used by the client/server flows.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # allow quick restarts while developing
        self.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)

    def _send_protocol_error(self, sock: _socket.socket, code: str, err: bytes = b"") -> str:
        """Send a protocol error payload to `sock` (best-effort) and close it.

        Returns a human-readable description suitable for logging.
        """
        payload = PROTOCOL_ERRORS.get(code, b"Unknown")
        if err:
            sock.sendall(payload + b"[" + err + b"]")
        else:
            sock.sendall(payload)
        sock.close()
        if err:
            decoded = err.decode(errors="ignore")
            return f"Protocol error: {code} [{decoded}]"
        return f"Protocol error: {code}"

    def bind(self, address: Tuple[str, int]):
        super().bind(address)
        # default listen backlog
        self.listen(5)

    def recv_exact(self, sock: _socket.socket, n: int) -> bytes:
        """Read exactly n bytes from sock or return b'' on EOF.

        This helper avoids partial reads when the protocol expects fixed
        length fields.
        """
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                return b""
            buf += chunk
        return buf

    # Client-side API
    def connect(self, address: Tuple[str, int], server: object) -> Optional[str]:
        """Connect to an upstream proxy listener and request a backend.

        `server` may be an integer index/key or a string name.
        Returns None on success or a string error message on failure.
        """
        super().connect(address)
        # send VERSION
        self.sendall(VERSION.encode())
        resp = self.recv(128)
        if resp != b"OK":
            return self._send_protocol_error(self, "no_support", resp)

        raw = self.recv_exact(self, 4)
        if not raw:
            return self._send_protocol_error(self, "proxy_error", b"missing_server_count")
        # server count is ignored by the client, but read for protocol sync
        _ = int.from_bytes(raw, "big")
        self.sendall(b"OK")

        # Support integer index or string key
        if isinstance(server, int):
            self.sendall(b"i" + int(server).to_bytes(4, "big"))
        else:
            name = str(server).encode()
            self.sendall(b"s" + len(name).to_bytes(4, "big") + name)

        resp = self.recv(128)
        if resp == b"OK":
            return None
        return self._send_protocol_error(self, "proxy_error", resp)

    # Server-side helpers
    def accept(self) -> Tuple[_socket.socket, Tuple[str, int]]:
        return super().accept()

    def handle_client(self, cs: _socket.socket, addr) -> Optional[str]:
        """Handle an incoming client connection and either proxy it or
        speak the small selection protocol to connect it to a backend.
        """
        # Read an initial buffer to help detect HTTP requests without
        # fragmenting the request data that should go to an HTTP backend.
        initial = cs.recv(4096)
        if not initial:
            return self._send_protocol_error(cs, "client_error", b"empty")

        # Rough HTTP detection by common methods
        http_methods = (b"GET ", b"POST ", b"HEAD ", b"PUT ", b"DELETE ", b"OPTIONS ")
        if any(initial.startswith(m) for m in http_methods):
            # If an 'http' backend exists, forward; otherwise respond with a
            # small HTML message.
            http_backend = config.get("http") if isinstance(config, dict) else None

            if http_backend is None:
                body = b"<h1>This is not a website!</h1>"
                headers = (
                    b"HTTP/1.0 200 OK\r\n"
                    b"Content-Type: text/html; charset=utf-8\r\n"
                    + f"Content-Length: {len(body)}\r\n".encode()
                    + b"\r\n"
                )
                cs.sendall(headers + body)
                time.sleep(0.5)
                cs.close()
                return "HTTP Client Tried to connect (no http backend)"

            sock = _socket.socket()
            sock.settimeout(10)
            sock.connect((http_backend["host"], http_backend["port"]))
            sock.sendall(initial)
            return self._proxy_between(cs, sock)

        # Not HTTP — treat the initial buffer as the start of the proxy protocol.
        if len(initial) < len(VERSION):
            rest = self.recv_exact(cs, len(VERSION) - len(initial))
            if not rest:
                return self._send_protocol_error(cs, "no_support", initial)
            ver = initial + rest
        else:
            ver = initial[: len(VERSION)]

        if ver != VERSION.encode():
            return self._send_protocol_error(cs, "no_support", ver)

        cs.sendall(b"OK")
        cs.sendall(len(config).to_bytes(4, "big"))

        ack = self.recv_exact(cs, len(b"OK"))
        if ack != b"OK":
            return self._send_protocol_error(cs, "client_error", ack)

        # Read server selection marker
        marker = cs.recv(1)
        if not marker:
            return self._send_protocol_error(cs, "client_error", b"missing_id")

        # Resolve selected backend based on marker
        if marker == b"i":
            raw = self.recv_exact(cs, 4)
            if not raw:
                return self._send_protocol_error(cs, "client_error", b"missing_id")
            sid = int.from_bytes(raw, "big")
            if isinstance(config, dict):
                if sid in config:
                    server = config[sid]
                else:
                    try:
                        server = list(config.values())[sid]
                    except IndexError:
                        return self._send_protocol_error(cs, "invalid_server", raw)
            else:
                try:
                    server = config[sid]
                except (KeyError, IndexError):
                    return self._send_protocol_error(cs, "invalid_server", raw)

        elif marker == b"s":
            llen = self.recv_exact(cs, 4)
            if not llen:
                return self._send_protocol_error(cs, "client_error", b"missing_name_len")
            ln = int.from_bytes(llen, "big")
            name = cs.recv(ln).decode()
            if isinstance(config, dict):
                if name in config:
                    server = config[name]
                else:
                    return self._send_protocol_error(cs, "invalid_server", name.encode())
            else:
                return self._send_protocol_error(cs, "invalid_server", name.encode())

        else:
            # Legacy path: first byte was part of a 4-byte integer id
            rest = self.recv_exact(cs, 3)
            if not rest:
                return self._send_protocol_error(cs, "client_error", b"missing_id")
            raw = marker + rest
            sid = int.from_bytes(raw, "big")
            if isinstance(config, dict):
                if sid in config:
                    server = config[sid]
                else:
                    try:
                        server = list(config.values())[sid]
                    except IndexError:
                        return self._send_protocol_error(cs, "invalid_server", raw)
            else:
                try:
                    server = config[sid]
                except (KeyError, IndexError):
                    return self._send_protocol_error(cs, "invalid_server", raw)

        cs.sendall(b"OK")
        sock = _socket.socket()
        sock.settimeout(10)
        sock.connect((server["host"], server["port"]))

        sock.setblocking(False)
        cs.setblocking(False)
        return self._proxy_between(cs, sock)

    def _proxy_between(self, cs: _socket.socket, sock: _socket.socket) -> Optional[str]:
        """Proxy data between client _socket `cs` and backend `sock` using selectors.

        This will forward data until one side closes the connection.
        """
        # Print peer names (allow exception to propagate if it fails)
        print(f"Proxying {':'.join(map(str, cs.getpeername()))} -> {':'.join(map(str, sock.getpeername()))}")

        sock.setblocking(False)
        cs.setblocking(False)
        sel = selectors.DefaultSelector()
        sel.register(cs, selectors.EVENT_READ, "client")
        sel.register(sock, selectors.EVENT_READ, "server")

        while True:
            events = sel.select(timeout=1)
            if not events:
                continue
            for key, _ in events:
                s = key.fileobj
                role = key.data
                try:
                    data = s.recv(4096)
                except BlockingIOError:
                    continue
                except ConnectionResetError:
                    return None

                if DEBUG:
                    print(data)

                if not data:
                    # peer closed; clean up both sides and exit
                    _cleanup_pair(sel, cs, sock)
                    return None

                # Forward data; let send failures propagate
                if role == "client":
                    sock.sendall(data)
                else:
                    cs.sendall(data)

def _safe_close(sock: Optional[_socket.socket]) -> None:
    """Close a _socket if not None, ignoring all exceptions."""
    if sock is None:
        return
    sock.close()

def _safe_unregister(sel: selectors.BaseSelector, sock: _socket.socket) -> None:
    """Unregister a fileobj from selector, ignoring errors."""
    sel.unregister(sock)

def _cleanup_pair(sel: selectors.BaseSelector, cs: _socket.socket, sock: _socket.socket) -> None:
    """Unregister and close two _sockets, best-effort."""
    _safe_unregister(sel, cs)
    _safe_unregister(sel, sock)
    _safe_close(cs)
    _safe_close(sock)

def _accept_loop(listener: _socket, stop_event: threading.Event, workers: List[threading.Thread]):
    while not stop_event.is_set():
        try:
            cs, addr = listener.accept()
        except OSError:
            break
        t = threading.Thread(target=_client_worker, args=(listener, cs, addr), daemon=True)
        workers.append(t)
        t.start()

def _client_worker(listener: _socket, cs: _socket.socket, addr):
    err = listener.handle_client(cs, addr)
    if err:
        print(f'client {addr} error: {err}')

DEBUG = False

if __name__ == '__main__':
    config = json.load(open(sys.argv[1]))
    with socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
        s.bind(('0.0.0.0', 8080))
        print('Proxy listening on 0.0.0.0:8080')

        stop_event = threading.Event()
        workers: List[threading.Thread] = []
        accept_thread = threading.Thread(target=_accept_loop, args=(s, stop_event, workers), daemon=False)
        accept_thread.start()

        try:
            while not stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            print('Shutting down...')
            stop_event.set()
            s.close()
            accept_thread.join(timeout=5)

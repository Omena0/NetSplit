import os
import sys
import socket as _socket
import selectors
import pytest

# Ensure the repository root is on sys.path so tests can import the top-level module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from netSplit import socket as NetSocket, PROTOCOL_ERRORS, _safe_close, _safe_unregister


class DummySock:
    """Minimal dummy object that mimics a socket for unregister tests."""

    def __init__(self, fileno: int = 1):
        self._fileno = fileno

    def fileno(self):
        return self._fileno


def test_recv_exact_reads_full_data(tmp_path, monkeypatch):
    # Create a pair of connected sockets
    srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    cli = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    cli.connect(('127.0.0.1', port))
    conn, _ = srv.accept()

    try:
        ns = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)

        # Send data in two parts from server side
        conn.sendall(b'hello')

        # Use recv_exact to read 5 bytes
        got = ns.recv_exact(cli, 5)
        assert got == b'hello'

        # sending more
        conn.sendall(b'world')
        got2 = ns.recv_exact(cli, 5)
        assert got2 == b'world'
    finally:
        conn.close()
        cli.close()
        srv.close()


def test_recv_exact_eof(tmp_path):
    # Create connected sockets and close peer mid-read
    srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    cli = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    cli.connect(('127.0.0.1', port))
    conn, _ = srv.accept()

    try:
        ns = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
        # Close server side to simulate EOF
        conn.close()
        got = ns.recv_exact(cli, 4)
        assert got == b''
    finally:
        cli.close()
        srv.close()


def test_safe_unregister_and_close_no_errors():
    sel = selectors.DefaultSelector()
    dummy = DummySock(10)

    # Register the dummy object then unregister using helper
    sel.register(dummy, selectors.EVENT_READ)
    # Should not raise
    _safe_unregister(sel, dummy)

    # Double-unregister should not raise either
    _safe_unregister(sel, dummy)

    # _safe_close should tolerate None and a real socket
    _safe_close(None)
    s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    _safe_close(s)


def test_protocol_error_payloads_present():
    # Ensure the mapping contains expected keys and byte values
    assert 'no_support' in PROTOCOL_ERRORS
    assert isinstance(PROTOCOL_ERRORS['no_support'], bytes)
    assert PROTOCOL_ERRORS['client_error'].startswith(b'E')

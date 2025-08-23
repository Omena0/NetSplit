import os
import sys
import socket as _socket
import threading
import time

# Ensure project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import netSplit
from netSplit import socket as NetSocket, PROTOCOL_ERRORS


def _start_mock_server(handler):
    """Start a TCP server thread that runs handler(conn) for each accept.

    The handler is responsible for reading/writing the accepted socket.
    Returns the (port, thread, server_socket) tuple.
    """
    srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def _run():
        try:
            conn, _ = srv.accept()
            handler(conn)
        finally:
            try:
                srv.close()
            except Exception:
                pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return port, t, srv


def test_client_connect_index_success():
    # Server that performs the expected handshake and accepts index 0
    def handler(conn: _socket.socket):
        try:
            # read version
            v = conn.recv(len(netSplit.VERSION))
            assert v == netSplit.VERSION.encode()
            # send OK + count
            conn.sendall(b'OK')
            conn.sendall((1).to_bytes(4, 'big'))
            # read client OK
            ack = conn.recv(2)
            assert ack == b'OK'
            # read selection marker and index
            marker = conn.recv(1)
            assert marker == b'i'
            raw = conn.recv(4)
            sid = int.from_bytes(raw, 'big')
            assert sid == 0
            # reply OK
            conn.sendall(b'OK')
        finally:
            try:
                conn.close()
            except Exception:
                pass

    port, th, srv = _start_mock_server(handler)

    cli = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
    try:
        res = cli.connect(('127.0.0.1', port), 0)
        assert res is None
    finally:
        try:
            cli.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass


def test_client_connect_name_success():
    def handler(conn: _socket.socket):
        try:
            v = conn.recv(len(netSplit.VERSION))
            assert v == netSplit.VERSION.encode()
            conn.sendall(b'OK')
            conn.sendall((1).to_bytes(4, 'big'))
            ack = conn.recv(2)
            assert ack == b'OK'
            marker = conn.recv(1)
            assert marker == b's'
            llen = conn.recv(4)
            ln = int.from_bytes(llen, 'big')
            name = conn.recv(ln)
            assert name == b'web'
            conn.sendall(b'OK')
        finally:
            try:
                conn.close()
            except Exception:
                pass

    port, th, srv = _start_mock_server(handler)
    cli = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
    try:
        res = cli.connect(('127.0.0.1', port), 'web')
        assert res is None
    finally:
        try:
            cli.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass


def test_client_connect_no_support():
    # Server replies with a non-OK greeting
    def handler(conn: _socket.socket):
        try:
            # read version
            _ = conn.recv(len(netSplit.VERSION))
            conn.sendall(b'NOPE')
        finally:
            try:
                conn.close()
            except Exception:
                pass

    port, th, srv = _start_mock_server(handler)
    cli = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
    try:
        res = cli.connect(('127.0.0.1', port), 0)
        assert isinstance(res, str)
        assert 'no_support' in res
    finally:
        try:
            cli.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass


def test_client_connect_missing_count():
    # Server sends OK then closes before sending 4-byte count
    def handler(conn: _socket.socket):
        try:
            _ = conn.recv(len(netSplit.VERSION))
            conn.sendall(b'OK')
            # close immediately
        finally:
            try:
                conn.close()
            except Exception:
                pass

    port, th, srv = _start_mock_server(handler)
    cli = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
    try:
        res = cli.connect(('127.0.0.1', port), 0)
        assert isinstance(res, str)
        assert 'proxy_error' in res
    finally:
        try:
            cli.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass

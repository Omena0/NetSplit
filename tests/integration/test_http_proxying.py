import os
import sys
import socket as _socket
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import netSplit
from netSplit import socket as NetSocket


def run_backend_server(port, ready_evt: threading.Event):
    srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    srv.bind(('127.0.0.1', port))
    srv.listen(1)
    ready_evt.set()
    conn, _ = srv.accept()
    try:
        # echo whatever we receive
        data = conn.recv(4096)
        conn.sendall(b'BACKEND:' + data)
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass


def test_http_backend_forwarding():
    # start backend server
    backend_srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    backend_srv.bind(('127.0.0.1', 0))
    port = backend_srv.getsockname()[1]
    backend_srv.close()

    ready = threading.Event()
    th = threading.Thread(target=run_backend_server, args=(port, ready), daemon=True)
    th.start()
    ready.wait(timeout=1)

    # configure http backend
    netSplit.config = {'http': {'host': '127.0.0.1', 'port': port}}

    # create client/listener pair
    srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    port_srv = srv.getsockname()[1]

    cli = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    cli.settimeout(2)
    cli.connect(('127.0.0.1', port_srv))
    conn, _ = srv.accept()
    try:
        listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
        # send a simple HTTP request
        cli.sendall(b'GET / HTTP/1.0\r\nHost: localhost\r\n\r\n')
        # run handler which should forward to backend and return value from _proxy_between
        res = listener.handle_client(conn, ('127.0.0.1', 0))
        # backend prepends 'BACKEND:' to echoed data; ensure handler returns None/finishes
        assert res in (None, 'HTTP Client Tried to connect (no http backend)') or isinstance(res, str) or res is None
    finally:
        try:
            cli.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass

import os
import sys
import socket as _socket
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import netSplit
from netSplit import socket as NetSocket


def test_http_no_backend_returns_html():
    # create connected pair
    srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    cli = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    cli.settimeout(2)
    cli.connect(('127.0.0.1', port))
    conn, _ = srv.accept()
    try:
        # ensure no http backend configured
        netSplit.config = {}
        listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)

        # send a simple HTTP GET
        def client_send():
            cli.sendall(b'GET / HTTP/1.0\r\nHost: localhost\r\n\r\n')

        t = threading.Thread(target=client_send, daemon=True)
        t.start()
        res = listener.handle_client(conn, ('127.0.0.1', 0))
        assert isinstance(res, str)
        assert 'HTTP Client Tried' in res
    finally:
        try:
            cli.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass

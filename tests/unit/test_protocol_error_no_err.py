import os
import sys
import socket as _socket

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import netSplit
from netSplit import socket as NetSocket


def make_connected_pair():
    srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    cli = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    cli.settimeout(2)
    cli.connect(('127.0.0.1', port))
    conn, _ = srv.accept()
    conn.settimeout(2)
    return cli, conn, srv


def test_send_protocol_error_without_err_closes_peer():
    cli, conn, srv = make_connected_pair()
    try:
        s = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
        desc = s._send_protocol_error(conn, 'proxy_error')
        assert 'proxy_error' in desc
        # peer should be closed
        try:
            conn.sendall(b'x')
            closed = False
        except Exception:
            closed = True
        assert closed
    finally:
        try:
            cli.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass

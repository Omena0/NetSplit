import os
import sys
import socket as _socket
import threading

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


def test_selection_by_name_returns_invalid_for_missing():
    netSplit.config = {'exists': {'host': '127.0.0.1', 'port': 1}}
    cli, conn, srv = make_connected_pair()
    try:
        listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
        th = threading.Thread(target=listener.handle_client, args=(conn, ('127.0.0.1', 0)), daemon=True)
        th.start()

        cli.sendall(netSplit.VERSION.encode())
        # robustly receive OK and 4-byte count (may be coalesced)
        data = cli.recv(128)
        assert data.startswith(b'OK')
        remaining = data[2:]
        if len(remaining) >= 4:
            raw = remaining[:4]
        else:
            need = 4 - len(remaining)
            rest = cli.recv(need)
            raw = remaining + rest
        cli.sendall(b'OK')
        name = b'missing'
        cli.sendall(b's' + len(name).to_bytes(4, 'big') + name)
        got = cli.recv(1024)
        assert got.startswith(netSplit.PROTOCOL_ERRORS['invalid_server'])
    finally:
        try:
            cli.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass


def test_selection_by_index_list_style_invalid():
    netSplit.config = [{'host': '127.0.0.1', 'port': 1}]
    cli, conn, srv = make_connected_pair()
    try:
        listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
        th = threading.Thread(target=listener.handle_client, args=(conn, ('127.0.0.1', 0)), daemon=True)
        th.start()

        cli.sendall(netSplit.VERSION.encode())
        # robustly receive OK and 4-byte count (may be coalesced)
        data = cli.recv(128)
        assert data.startswith(b'OK')
        remaining = data[2:]
        if len(remaining) >= 4:
            raw = remaining[:4]
        else:
            need = 4 - len(remaining)
            rest = cli.recv(need)
            raw = remaining + rest
        cli.sendall(b'OK')
        # send out-of-range index
        cli.sendall(b'i' + (9999).to_bytes(4, 'big'))
        got = cli.recv(1024)
        assert got.startswith(netSplit.PROTOCOL_ERRORS['invalid_server'])
    finally:
        try:
            cli.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass

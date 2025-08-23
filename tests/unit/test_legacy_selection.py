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


def test_legacy_selection_list_index_and_invalid():
    cli, conn, srv = make_connected_pair()
    try:
        # set config to a list to force list-style indexing
        netSplit.config = [{'host': '127.0.0.1', 'port': 1}]
        listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)

        # start handler in a thread
        th = threading.Thread(target=listener.handle_client, args=(conn, ('127.0.0.1', 0)), daemon=True)
        th.start()

        # client handshake
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
        # legacy marker: send a first byte that is not 'i' or 's', then 3 bytes
        raw_id = (9999).to_bytes(4, 'big')
        cli.sendall(raw_id)
        # should receive invalid_server since list index 9999 is out of range
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

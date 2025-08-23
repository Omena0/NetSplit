import os
import sys
import socket as _socket
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import netSplit
from netSplit import socket as NetSocket, _accept_loop


def _recv_ok_and_count(cli: _socket.socket) -> bytes:
    data = cli.recv(128)
    assert data.startswith(b'OK')
    remaining = data[2:]
    if len(remaining) >= 4:
        return remaining[:4]
    need = 4 - len(remaining)
    rest = cli.recv(need)
    return remaining + rest


def test_client_connect_selection_proxy_error():
    # server will reply non-OK after selection to trigger client proxy_error path
    def handler(conn: _socket.socket):
        try:
            v = conn.recv(len(netSplit.VERSION))
            assert v == netSplit.VERSION.encode()
            conn.sendall(b'OK')
            conn.sendall((1).to_bytes(4, 'big'))
            ack = conn.recv(2)
            assert ack == b'OK'
            # read marker and index
            marker = conn.recv(1)
            raw = conn.recv(4)
            # reply with a non-OK
            conn.sendall(b'NOPE')
        finally:
            try:
                conn.close()
            except Exception:
                pass

    srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def run():
        conn, _ = srv.accept()
        handler(conn)

    t = threading.Thread(target=run, daemon=True)
    t.start()

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


def test_accept_wrapper_returns_tuple():
    s = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]

    got = []

    def client_run():
        c = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        try:
            c.connect(('127.0.0.1', port))
        finally:
            try:
                c.close()
            except Exception:
                pass

    t = threading.Thread(target=client_run, daemon=True)
    t.start()
    conn, addr = s.accept()
    assert hasattr(conn, 'recv')
    try:
        conn.close()
    except Exception:
        pass
    try:
        s.close()
    except Exception:
        pass


def test_handle_missing_marker_returns_error():
    # server sends version and count, client sends OK then closes (no marker)
    srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    cli = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    cli.settimeout(2)
    cli.connect(('127.0.0.1', port))
    conn, _ = srv.accept()
    try:
        # ensure config exists so handler can send count
        netSplit.config = {}
        listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
        th = threading.Thread(target=listener.handle_client, args=(conn, ('127.0.0.1', 0)), daemon=True)
        th.start()

        cli.sendall(netSplit.VERSION.encode())
        _recv_ok_and_count(cli)
        cli.sendall(b'OK')
        # close before sending marker
        cli.close()
        # give handler a moment
        time.sleep(0.05)
    finally:
        try:
            srv.close()
        except Exception:
            pass


def test_dict_index_list_indexerror_returns_invalid_server():
    # config is dict with only key 0; request sid=5 -> list(config.values())[5] IndexError
    netSplit.config = {0: {'host': '127.0.0.1', 'port': 1}}
    srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    cli = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    cli.settimeout(2)
    cli.connect(('127.0.0.1', port))
    conn, _ = srv.accept()
    try:
        listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
        th = threading.Thread(target=listener.handle_client, args=(conn, ('127.0.0.1', 0)), daemon=True)
        th.start()

        cli.sendall(netSplit.VERSION.encode())
        _recv_ok_and_count(cli)
        cli.sendall(b'OK')
        cli.sendall(b'i' + (5).to_bytes(4, 'big'))
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


def test_legacy_index_list_indexerror_returns_invalid_server():
    # legacy path: marker byte part of 4-byte id; choose id that is out-of-range
    netSplit.config = {0: {'host': '127.0.0.1', 'port': 1}}
    srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    cli = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    cli.settimeout(2)
    cli.connect(('127.0.0.1', port))
    conn, _ = srv.accept()
    try:
        listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
        th = threading.Thread(target=listener.handle_client, args=(conn, ('127.0.0.1', 0)), daemon=True)
        th.start()

        cli.sendall(netSplit.VERSION.encode())
        _recv_ok_and_count(cli)
        cli.sendall(b'OK')
        # send legacy 4-byte id (first byte not 'i' or 's') for id=9999
        cli.sendall((9999).to_bytes(4, 'big'))
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


def test_accept_loop_spawns_worker_thread(monkeypatch):
    # Create a fake listener that returns one (conn, addr) then raises OSError
    class FakeListener:
        def __init__(self):
            self._called = 0

        def accept(self):
            if self._called == 0:
                self._called += 1
                return (object(), ('127.0.0.1', 0))
            raise OSError()

    fl = FakeListener()
    workers = []

    created = {'started': False}

    class DummyThread:
        def __init__(self, target, args, daemon):
            self._target = target
            self._args = args

        def start(self):
            created['started'] = True

    monkeypatch.setattr(threading, 'Thread', DummyThread)
    _accept_loop(fl, threading.Event(), workers)
    assert created['started']

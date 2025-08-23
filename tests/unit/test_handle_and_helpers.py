import os
import sys
import socket as _socket
import threading
import selectors
import time

# Ensure project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import netSplit
from netSplit import socket as NetSocket, _safe_unregister, _cleanup_pair, _accept_loop


# --- Tests for handle_client error branches ---


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


def test_handle_client_empty_initial():
    cli, conn, srv = make_connected_pair()
    try:
        # Close client so server sees empty on recv
        cli.close()
        listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
        res = listener.handle_client(conn, ('127.0.0.1', 12345))
        assert isinstance(res, str)
        assert 'empty' in res or 'client_error' in res
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass


def test_handle_client_short_version():
    cli, conn, srv = make_connected_pair()
    try:
        # Client sends only a short prefix of VERSION then closes. Use
        # VERSION[:-1] so the test remains valid even if VERSION length
        # changes (ensures a true prefix, not the full value).
        prefix = netSplit.VERSION[:-1] if len(netSplit.VERSION) > 1 else netSplit.VERSION[:0]
        cli.sendall(prefix.encode())
        cli.close()
        listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
        res = listener.handle_client(conn, ('127.0.0.1', 12345))
        assert isinstance(res, str)
        assert 'no_support' in res
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass


def test_handle_client_bad_version():
    cli, conn, srv = make_connected_pair()
    try:
        # send wrong version
        cli.sendall(b'BAD-VERSION-XYZ')
        listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
        res = listener.handle_client(conn, ('127.0.0.1', 12345))
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


def test_handle_client_bad_ack():
    # Server sends OK+count and expects OK ack; client replies with wrong ack
    def client_thread(port, ready_evt: threading.Event):
        c = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        c.connect(('127.0.0.1', port))
        # send VERSION
        c.sendall(netSplit.VERSION.encode())
        # receive OK+count
        data = c.recv(128)
        # signal ready
        ready_evt.set()
        # send wrong ack
        c.sendall(b'NO')
        # read error payload
        got = c.recv(1024)
        c.close()
        return got

    # create server socket
    srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    ready = threading.Event()
    # start listener handler after accept
    def server_run():
        conn, _ = srv.accept()
        listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
        # handle_client will block waiting for ack and then see wrong ack
        res = listener.handle_client(conn, ('127.0.0.1', 0))
        # return value used for assertion
        return res

    # Start client in a thread
    t_client = threading.Thread(target=client_thread, args=(port, ready), daemon=True)
    t_client.start()
    # ensure module-level config is defined so handler can send count
    netSplit.config = {}
    # accept and run server handler in main thread
    conn, _ = srv.accept()
    try:
        listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
        # handle_client should return an error when ack mismatches
        res = listener.handle_client(conn, ('127.0.0.1', 0))
        assert isinstance(res, str)
        assert 'client_error' in res or 'no_support' in res
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass


# --- Tests for proxy loop using fake selector and sockets ---

class FakeSocket:
    def __init__(self, peer, recv_seq):
        self._peer = peer
        self._recv_seq = list(recv_seq)
        self.sent = []
        self.closed = False

    def getpeername(self):
        return self._peer

    def setblocking(self, v):
        pass

    def recv(self, n):
        if not self._recv_seq:
            return b''
        v = self._recv_seq.pop(0)
        if isinstance(v, Exception):
            raise v
        return v

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        self.closed = True

    def fileno(self):
        return id(self) & 0xFFFF


class Key:
    def __init__(self, fileobj, data):
        self.fileobj = fileobj
        self.data = data


class FakeSelector:
    def __init__(self, events_sequence):
        # events_sequence is a list of lists of (fileobj, data) tuples
        self.events_sequence = [list(ev) for ev in events_sequence]
        self.registered = {}

    def register(self, sock, event, data):
        self.registered[sock] = data

    def unregister(self, sock):
        if sock not in self.registered:
            raise KeyError('not registered')
        del self.registered[sock]

    def select(self, timeout=None):
        if not self.events_sequence:
            time.sleep(0.01)
            return []
        ev = self.events_sequence.pop(0)
        return [(Key(fileobj, data), None) for (fileobj, data) in ev]


def test_proxy_between_forwards_and_cleans_up(monkeypatch):
    # client sends b'hello' then EOF; backend receives hello
    cs = FakeSocket(('127.0.0.1', 1), [b'hello', b''])
    backend = FakeSocket(('127.0.0.1', 2), [b'', b''])

    # events: first client readable, then client readable (EOF)
    events = [ [(cs, 'client')], [(cs, 'client')] ]
    fake_sel = FakeSelector(events)

    monkeypatch.setattr(selectors, 'DefaultSelector', lambda: fake_sel)

    s = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
    # call proxy between with fakes
    res = s._proxy_between(cs, backend)
    assert res is None
    # backend should have received the forwarded data
    assert any(b'hello' in chunk for chunk in backend.sent)
    # sockets should be marked closed
    assert cs.closed and backend.closed


def test_proxy_between_handles_blockingio(monkeypatch):
    # first call raises BlockingIOError, then returns EOF
    cs = FakeSocket(('127.0.0.1', 1), [BlockingIOError(), b''])
    backend = FakeSocket(('127.0.0.1', 2), [b'', b''])
    events = [ [(cs, 'client')], [(cs, 'client')] ]
    fake_sel = FakeSelector(events)
    monkeypatch.setattr(selectors, 'DefaultSelector', lambda: fake_sel)
    s = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
    res = s._proxy_between(cs, backend)
    assert res is None


def test_safe_unregister_swallowing(monkeypatch):
    class BadSelector:
        def unregister(self, sock):
            raise RuntimeError('boom')

    sel = BadSelector()
    # should not raise
    _safe_unregister(sel, object())


def test_cleanup_pair_calls(monkeypatch):
    # monkeypatch internal helpers to observe calls
    called = {'u': False, 'c': False}

    def fake_unregister(sel, sock):
        called['u'] = True

    def fake_close(sock):
        called['c'] = True

    monkeypatch.setattr(netSplit, '_safe_unregister', fake_unregister)
    monkeypatch.setattr(netSplit, '_safe_close', fake_close)

    sel = object()
    cs = object()
    sk = object()
    _cleanup_pair(sel, cs, sk)
    assert called['u'] and called['c']


def test_accept_loop_exits_immediately():
    class BadListener:
        def accept(self):
            raise OSError()

    stop_event = threading.Event()
    workers = []
    # Should return quickly without raising
    _accept_loop(BadListener(), stop_event, workers)


def test_proxy_between_server_to_client(monkeypatch):
    # backend sends data 'pong' and client should receive forwarded data
    cs = FakeSocket(('127.0.0.1', 1), [b'', b''])
    backend = FakeSocket(('127.0.0.1', 2), [b'pong', b''])

    # events: backend readable first, then backend EOF
    events = [ [(backend, 'server')], [(backend, 'server')] ]
    fake_sel = FakeSelector(events)
    monkeypatch.setattr(selectors, 'DefaultSelector', lambda: fake_sel)

    s = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
    res = s._proxy_between(cs, backend)
    assert res is None
    # client should have been sent the backend data
    assert any(b'pong' in chunk for chunk in cs.sent)


def test_handle_client_dict_index_selection():
    # Prepare a backend that sends a marker response
    def backend_run(conn):
        try:
            # wait for connection from proxy, then send RESP
            conn.sendall(b'RESP-DICT')
        finally:
            try:
                conn.close()
            except Exception:
                pass

    srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    t = threading.Thread(target=lambda: backend_run(srv.accept()[0]), daemon=True)
    t.start()

    # config as dict with numeric key
    netSplit.config = {0: {'host': '127.0.0.1', 'port': port}}

    # create client/conn pair
    cli = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    cli.settimeout(3)
    srv2 = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    srv2.bind(('127.0.0.1', 0))
    srv2.listen(1)
    port2 = srv2.getsockname()[1]
    c = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    c.connect(('127.0.0.1', port2))
    conn, _ = srv2.accept()

    try:
        # run handler in background
        listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
        th = threading.Thread(target=listener.handle_client, args=(conn, ('127.0.0.1', 0)), daemon=True)
        th.start()

        # perform client handshake
        c.sendall(netSplit.VERSION.encode())
        data = c.recv(128)
        # receive count
        raw = c.recv(4)
        c.sendall(b'OK')
        c.sendall(b'i' + (0).to_bytes(4, 'big'))
        # server should send OK and then backend data
        assert c.recv(128) == b'OK'
        got = c.recv(1024)
        assert b'RESP-DICT' in got
    finally:
        try:
            c.close()
        except Exception:
            pass
        try:
            srv2.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass


def test_handle_client_unknown_name_triggers_invalid_server():
    # backend not used; configure dict without the name
    netSplit.config = {'exists': {'host': '127.0.0.1', 'port': 1}}

    cli, conn, srv = make_connected_pair()
    try:
        # start server-side handler
        listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
        th = threading.Thread(target=listener.handle_client, args=(conn, ('127.0.0.1', 0)), daemon=True)
        th.start()

        # client handshake
        cli.sendall(netSplit.VERSION.encode())
        _ = cli.recv(128)
        _ = cli.recv(4)
        cli.sendall(b'OK')
        name = b'missing'
        cli.sendall(b's' + len(name).to_bytes(4, 'big') + name)
        # should receive invalid_server error
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


def test_client_worker_prints_error(capsys):
    # fake listener with handle_client returning an error string
    class FakeListener:
        def handle_client(self, cs, addr):
            return 'simulated error'

    # create a dummy socket pair
    cli, conn, srv = make_connected_pair()
    try:
        _client = FakeListener()
        # call worker which should print the error
        netSplit._client_worker(_client, conn, ('127.0.0.1', 0))
        captured = capsys.readouterr()
        assert 'simulated error' in captured.out
    finally:
        try:
            cli.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass


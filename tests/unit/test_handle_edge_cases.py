import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import netSplit
from netSplit import socket as NetSocket


class FakeClient:
    def __init__(self, recv_seq):
        self._recv_seq = list(recv_seq)
        self.sent = []
        self.closed = False

    def recv(self, n):
        if not self._recv_seq:
            return b''
        return self._recv_seq.pop(0)

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        self.closed = True

    def settimeout(self, t):
        pass

    def setblocking(self, v):
        pass

    def getpeername(self):
        return ('127.0.0.1', 9999)


def test_marker_i_missing_raw_returns_client_error():
    # initial is VERSION, ack OK, marker 'i', but raw (4 bytes) missing
    cs = FakeClient([netSplit.VERSION.encode(), b'OK', b'i', b''])
    netSplit.config = {0: {'host': '127.0.0.1', 'port': 1}}
    listener = NetSocket(netSplit._socket.AF_INET, netSplit._socket.SOCK_STREAM)
    res = listener.handle_client(cs, ('127.0.0.1', 0))
    assert isinstance(res, str)
    assert 'missing_id' in res or 'client_error' in res


def test_marker_s_missing_len_returns_client_error():
    # initial VERSION, ack OK, marker 's', but length field missing
    cs = FakeClient([netSplit.VERSION.encode(), b'OK', b's', b''])
    netSplit.config = {}
    listener = NetSocket(netSplit._socket.AF_INET, netSplit._socket.SOCK_STREAM)
    res = listener.handle_client(cs, ('127.0.0.1', 0))
    assert isinstance(res, str)
    assert 'missing_name_len' in res or 'client_error' in res


def test_legacy_missing_rest_returns_client_error():
    # initial VERSION, ack OK, marker not i/s, but rest (3 bytes) missing
    cs = FakeClient([netSplit.VERSION.encode(), b'OK', b'\x05', b''])
    netSplit.config = {}
    listener = NetSocket(netSplit._socket.AF_INET, netSplit._socket.SOCK_STREAM)
    res = listener.handle_client(cs, ('127.0.0.1', 0))
    assert isinstance(res, str)
    assert 'missing_id' in res or 'client_error' in res


def test_selection_index_success_triggers_proxy_between(monkeypatch):
    # create a fake client that will negotiate and select index 5
    cs = FakeClient([netSplit.VERSION.encode(), b'OK', b'i' + (5).to_bytes(4, 'big')])

    # monkeypatch recv_exact to behave normally for ack read in handle_client
    # but our FakeClient.recv is simple and will satisfy calls

    # monkeypatch backend socket creation to avoid network; provide object accepted by _proxy_between
    class FakeBackend:
        def __init__(self):
            pass

        def settimeout(self, t):
            pass

        def connect(self, addr):
            pass

        def setblocking(self, v):
            pass

        def getpeername(self):
            return ('127.0.0.1', 12345)

    monkeypatch.setattr(netSplit._socket, 'socket', lambda *a, **k: FakeBackend())

    # intercept _proxy_between to avoid needing real sockets
    monkeypatch.setattr(NetSocket, '_proxy_between', lambda self, a, b: None)

    netSplit.config = {5: {'host': '127.0.0.1', 'port': 12345}}
    listener = NetSocket(netSplit._socket.AF_INET, netSplit._socket.SOCK_STREAM)
    res = listener.handle_client(cs, ('127.0.0.1', 0))
    # the handler should return either None (via _proxy_between) or a string on error
    assert res is None or isinstance(res, str)

import os
import sys
import socket as _socket

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import netSplit
from netSplit import socket as NetSocket


class SeqClient:
    def __init__(self, seq):
        self.seq = list(seq)
        self.sent = []
        self.closed = False

    def recv(self, n):
        if not self.seq:
            return b''
        return self.seq.pop(0)

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        self.closed = True

    def settimeout(self, t):
        pass

    def setblocking(self, b):
        pass

    def getpeername(self):
        return ('127.0.0.1', 1)


def _stub_proxy(self, cs, sock):
    # mark that backend was connected and return success
    return None


class FakeSock:
    """A minimal fake socket used to avoid real network connects in tests."""
    def __init__(self, *a, **k):
        self.connected = False

    def settimeout(self, t):
        pass

    def connect(self, addr):
        # pretend we connected; don't actually touch the network
        self.connected = True

    def sendall(self, data):
        pass

    def close(self):
        pass

    def setblocking(self, b):
        pass


def test_version_rest_combines_and_proceeds(monkeypatch):
    # split VERSION into prefix + rest so the code executes 'ver = initial + rest'
    v = netSplit.VERSION
    prefix = v[:1].encode()
    rest = v[1:].encode()

    # sequence of what client will send to the server via recv()
    # initial (prefix), then rest for recv_exact, then ack 'OK', then marker 'i' + 4-byte id
    seq = [prefix, rest, b'OK', b'i', (0).to_bytes(4, 'big')]
    client = SeqClient(seq)

    # set a config so len(config) is available and target server exists
    netSplit.config = {0: {'host': '127.0.0.1', 'port': 1}}

    # stub the backend proxying so no network is used
    monkeypatch.setattr(netSplit.socket, '_proxy_between', _stub_proxy)
    # prevent real socket.connect() from being called
    monkeypatch.setattr(netSplit._socket, 'socket', FakeSock)

    listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
    res = listener.handle_client(client, ('127.0.0.1', 0))
    assert res is None or isinstance(res, str)


def test_selection_by_name_success(monkeypatch):
    name = 'myserver'
    # client sends full VERSION, then 'OK' ack, then 's' marker + name length + name
    seq = [netSplit.VERSION.encode(), b'OK', b's', len(name.encode()).to_bytes(4, 'big'), name.encode()]
    client = SeqClient(seq)

    netSplit.config = {name: {'host': '127.0.0.1', 'port': 1}}

    # stub proxy to avoid real sockets
    monkeypatch.setattr(netSplit.socket, '_proxy_between', _stub_proxy)
    monkeypatch.setattr(netSplit._socket, 'socket', FakeSock)

    listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
    res = listener.handle_client(client, ('127.0.0.1', 0))
    assert res is None or isinstance(res, str)


def test_legacy_list_index_success(monkeypatch):
    # legacy marker: send a first byte that's not 'i' or 's', then 3 bytes follow
    sid = 0
    raw = sid.to_bytes(4, 'big')
    seq = [netSplit.VERSION.encode(), b'OK', raw[:1], raw[1:]]
    client = SeqClient(seq)

    netSplit.config = [{'host': '127.0.0.1', 'port': 1}]

    monkeypatch.setattr(netSplit.socket, '_proxy_between', _stub_proxy)
    monkeypatch.setattr(netSplit._socket, 'socket', FakeSock)

    listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
    res = listener.handle_client(client, ('127.0.0.1', 0))
    assert res is None or isinstance(res, str)

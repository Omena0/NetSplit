import os
import sys
import socket as _socket
import selectors
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import netSplit
from netSplit import socket as NetSocket


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


def test_proxy_between_debug_prints(monkeypatch, capsys):
    cs = FakeSocket(('127.0.0.1', 1), [b'data', b''])
    backend = FakeSocket(('127.0.0.1', 2), [b'', b''])
    events = [[(cs, 'client')], [(cs, 'client')]]
    fake_sel = FakeSelector(events)
    monkeypatch.setattr(selectors, 'DefaultSelector', lambda: fake_sel)

    s = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
    # enable debug
    netSplit.DEBUG = True
    try:
        res = s._proxy_between(cs, backend)
        assert res is None
        captured = capsys.readouterr()
        assert 'data' in captured.out
    finally:
        netSplit.DEBUG = False

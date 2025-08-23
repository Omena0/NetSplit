import os
import sys
import socket as _socket

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import netSplit
from netSplit import socket as NetSocket


def test_legacy_marker_with_dict_key(monkeypatch):
    # legacy marker: first byte not 'i' or 's' and config is a dict with integer key
    sid = 0
    raw = sid.to_bytes(4, 'big')
    seq = [netSplit.VERSION.encode(), b'OK', raw[:1], raw[1:]]
    client = type('C', (), {
        'seq': list(seq),
        'sent': [],
        'closed': False,
        'recv': lambda self, n: self.seq.pop(0) if self.seq else b'',
        'sendall': lambda self, data: self.sent.append(data),
        'close': lambda self: setattr(self, 'closed', True),
        'settimeout': lambda self, t: None,
        'setblocking': lambda self, b: None,
        'getpeername': lambda self: ('127.0.0.1', 1),
    })()

    # config is a dict with integer key -> should hit the 'sid in config' branch
    netSplit.config = {0: {'host': '127.0.0.1', 'port': 1}}

    # Prevent real network connects and proxying
    class FakeSock:
        def __init__(self, *a, **k):
            pass
        def settimeout(self, t):
            pass
        def connect(self, addr):
            pass
        def setblocking(self, b):
            pass

    monkeypatch.setattr(netSplit._socket, 'socket', FakeSock)
    monkeypatch.setattr(netSplit.socket, '_proxy_between', lambda self, cs, sock: None)

    listener = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
    res = listener.handle_client(client, ('127.0.0.1', 0))
    assert res is None or isinstance(res, str)


def test_proxy_select_empty_then_shutdown(monkeypatch):
    # Cover the 'if not events: continue' path by making the selector
    # return an empty list once, then return an event that triggers
    # ConnectionResetError to end the loop.

    class FakeKey:
        def __init__(self, fileobj, data):
            self.fileobj = fileobj
            self.data = data

    class FakeSelector:
        def __init__(self):
            self.calls = 0
        def register(self, sock, ev, data=None):
            # noop
            pass
        def unregister(self, sock):
            pass
        def select(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                return []
            # second call: return an event whose fileobj.recv raises
            class BadSock:
                def getpeername(self):
                    return ('1.2.3.4', 9999)
                def recv(self, n):
                    raise ConnectionResetError
            return [ (FakeKey(BadSock(), 'client'), None) ]

    # Fake sockets passed to _proxy_between
    class CS:
        def getpeername(self):
            return ('127.0.0.1', 1234)
        def setblocking(self, b):
            pass

    class BACK:
        def getpeername(self):
            return ('9.9.9.9', 4321)
        def setblocking(self, b):
            pass

    monkeypatch.setattr(netSplit.selectors, 'DefaultSelector', lambda: FakeSelector())

    ns = NetSocket(_socket.AF_INET, _socket.SOCK_STREAM)
    cs = CS()
    back = BACK()
    # Should return None (clean shutdown on ConnectionResetError)
    res = ns._proxy_between(cs, back)
    assert res is None

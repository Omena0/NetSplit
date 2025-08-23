import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import netSplit
from netSplit import socket as NetSocket


class FakeClient:
    def __init__(self, recv_sequence):
        # recv_sequence: list of bytes or Exceptions to be returned/raised
        self._recv = list(recv_sequence)
        self.sent = []
        self.closed = False

    def recv(self, n):
        if not self._recv:
            return b''
        v = self._recv.pop(0)
        if isinstance(v, Exception):
            raise v
        return v

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        self.closed = True

    def settimeout(self, t):
        pass

    def setblocking(self, b):
        pass

    def getpeername(self):
        return ('127.0.0.1', 1234)


def test_short_version_missing_rest():
    # initial shorter than VERSION and recv_exact returns b'' -> no_support
    prefix = netSplit.VERSION[:-1] if len(netSplit.VERSION) > 1 else b''
    seq = [prefix.encode(), b'']
    fake = FakeClient(seq)
    listener = NetSocket()
    res = listener.handle_client(fake, ('127.0.0.1', 0))
    assert isinstance(res, str)
    assert 'no_support' in res
    # ensure fake got a protocol error payload and was closed
    assert fake.closed or any(b'E' in chunk for chunk in fake.sent)


def test_invalid_server_name_returns_protocol_error():
    # full VERSION, client ack, then 's' marker with a missing name
    name = b'missing'
    seq = [netSplit.VERSION.encode(), b'OK', b's', len(name).to_bytes(4, 'big'), name]
    fake = FakeClient(seq)
    # ensure no matching name in config
    netSplit.config = {}
    listener = NetSocket()
    res = listener.handle_client(fake, ('127.0.0.1', 0))
    assert isinstance(res, str)
    assert 'invalid_server' in res
    # ensure protocol error was sent and socket closed
    assert fake.closed or any(netSplit.PROTOCOL_ERRORS['invalid_server'].startswith(chunk) for chunk in fake.sent)


def test_legacy_index_out_of_range_triggers_invalid_server():
    # full VERSION, client ack, legacy marker (first byte of id) + 3 bytes rest
    # craft a large sid that is out of range for a small config
    sid = 9999
    raw_id = sid.to_bytes(4, 'big')
    seq = [netSplit.VERSION.encode(), b'OK', raw_id[:1], raw_id[1:]]
    fake = FakeClient(seq)
    netSplit.config = {0: {'host': '127.0.0.1', 'port': 1}}
    listener = NetSocket()
    res = listener.handle_client(fake, ('127.0.0.1', 0))
    assert isinstance(res, str)
    assert 'invalid_server' in res
    assert fake.closed or any(netSplit.PROTOCOL_ERRORS['invalid_server'].startswith(chunk) for chunk in fake.sent)

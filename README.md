
# NetSplit

[![Build](https://github.com/Omena0/NetSplit/actions/workflows/publish.yml/badge.svg?branch=master)](https://github.com/Omena0/NetSplit/actions/workflows/publish.yml)
[![Tests](https://github.com/Omena0/NetSplit/actions/workflows/pytest.yml/badge.svg?branch=master)](https://github.com/Omena0/NetSplit/actions/workflows/pytest.yml)
[![Coverage](https://codecov.io/gh/Omena0/NetSplit/branch/master/graph/badge.svg)](https://codecov.io/gh/Omena0/NetSplit)

[PyPI Package](https://pypi.org/project/PyNetSplit/)

Split a single tcp/ip connection between multiple servers.

Wait isn't this just NAT....

## Usage

```sh
py netsplit.py config.json
```

## Config

```jsonc
{
    "http": { // Special route that forwards web browsers
        "host": "127.0.0.1",
        "port": 8000
    },
    "0": {    // Server ID (SID), this is what you will put in s.connect(<addr>, <sid>)
        "host": "127.0.0.1",
        "port": 5000
    }
    ... // You can have as many as you want
}
```

## Client usage

```py
import netSplit

s = netSplit.socket()              # Create socket
s.connect(('127.0.0.1', 8080), 0)  # Connect to the proxy, and ask it to forward us to server 0

# Simple echo client
while True:
    s.send(input('> ').encode())
    print(s.recv(2048).decode())

```

## Server usage

The server does not have to be built with netSplit.

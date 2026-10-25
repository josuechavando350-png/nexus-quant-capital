"""Servidor WebSocket falso (sin TLS, en localhost) para probar el cliente y las suscripciones sin red."""

import base64
import hashlib
import json
import socket
import struct
import threading

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class Conn:
    def __init__(self, sock):
        self.sock, self.buf = sock, b""

    def _exact(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("cliente cerró")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def handshake(self, accept=True, bad_key=False):
        while b"\r\n\r\n" not in self.buf:
            self.buf += self.sock.recv(4096)
        head, self.buf = self.buf.split(b"\r\n\r\n", 1)
        key = [ln.split(b":", 1)[1].strip() for ln in head.split(b"\r\n") if ln.lower().startswith(b"sec-websocket-key")][0]
        if not accept:
            self.sock.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            return
        acc = base64.b64encode(hashlib.sha1((key.decode() + GUID).encode()).digest())
        if bad_key:
            acc = b"x" + acc[1:]
        self.sock.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + acc + b"\r\n\r\n")

    def frame(self, op, payload, fin=True):
        n = len(payload)
        head = bytes([(0x80 if fin else 0) | op])
        if n < 126:
            head += bytes([n])
        elif n < 65536:
            head += bytes([126]) + struct.pack(">H", n)
        else:
            head += bytes([127]) + struct.pack(">Q", n)
        self.sock.sendall(head + payload)

    def send_json(self, obj):
        self.frame(0x1, json.dumps(obj).encode())

    def recv_client(self):
        """(opcode, carga) de un marco del cliente (los del cliente van enmascarados)."""
        b1, b2 = self._exact(2)
        assert b2 & 0x80, "el cliente debe enmascarar"
        n = b2 & 0x7F
        if n == 126:
            n = struct.unpack(">H", self._exact(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", self._exact(8))[0]
        mask = self._exact(4)
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(self._exact(n)))
        return b1 & 0x0F, data

    def recv_json(self):
        op, data = self.recv_client()
        return op, (json.loads(data) if op == 0x1 else data)


class FakeWsServer:
    """Atiende conexiones una tras otra con `handler(conn)`; `url` es ws://127.0.0.1:puerto/."""

    def __init__(self, handler, **handshake):
        self.handler, self.handshake = handler, handshake
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(4)
        self.url = f"ws://127.0.0.1:{self.srv.getsockname()[1]}/"
        self.connections = 0
        self.errors = []
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while True:
            try:
                s, _ = self.srv.accept()
            except OSError:
                return
            self.connections += 1
            c = Conn(s)
            try:
                c.handshake(**self.handshake)
                self.handler(c)
            except (ConnectionError, OSError, AssertionError) as e:
                self.errors.append(e)
            finally:
                try:
                    s.close()
                except OSError:
                    pass

    def close(self):
        self.srv.close()

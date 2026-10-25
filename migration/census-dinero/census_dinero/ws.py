"""Cliente WebSocket mínimo (RFC 6455) con la biblioteca estándar: lo justo para suscribirse a un RPC con `eth_subscribe`.

Sirve para recibir los trozos de Base (Flashblocks) empujados por el servidor en vez de preguntar cada 100 ms. Solo lectura:
manda las suscripciones y lee mensajes; nunca firma ni envía transacciones (el envío de JSON se limita a `eth_subscribe`).
"""

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import time
from urllib.parse import urlparse

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
ALLOWED_METHODS = frozenset({"eth_subscribe", "eth_unsubscribe"})


class WsError(Exception):
    pass


class WsClient:
    def __init__(self, url, timeout=10.0, wall=time.time):
        self.url, self.timeout, self.wall = url, timeout, wall
        self.sock = None
        self.buf = bytearray()
        self.pos = 0

    # -- conexión ----------------------------------------------------------------------------
    def connect(self):
        u = urlparse(self.url)
        if u.scheme not in ("ws", "wss"):
            raise WsError(f"esquema no soportado: {u.scheme}")
        port = u.port or (443 if u.scheme == "wss" else 80)
        raw = socket.create_connection((u.hostname, port), timeout=self.timeout)
        raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        if u.scheme == "wss":
            raw = ssl.create_default_context().wrap_socket(raw, server_hostname=u.hostname)
        key = base64.b64encode(os.urandom(16)).decode()
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        raw.sendall((f"GET {path} HTTP/1.1\r\nHost: {u.hostname}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                     f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        self.sock = raw
        try:
            head = self._read_head()
            status = head.split(b"\r\n", 1)[0]
            if b" 101" not in status:
                raise WsError(f"el servidor no aceptó el WebSocket: {status[:80].decode(errors='replace')}")
            accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest())
            if accept not in head:
                raise WsError("respuesta sin Sec-WebSocket-Accept válido")
        except BaseException:
            raw.close()                              # un apretón de manos fallido no deja el socket abierto
            self.sock = None
            raise
        return self

    def close(self):
        if self.sock is not None:
            try:
                self._send(0x8, b"")
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    # -- lectura -------------------------------------------------------------------------------
    def _fill(self):
        chunk = self.sock.recv(65536)
        if not chunk:
            raise WsError("conexión cerrada por el servidor")
        if self.pos > 1 << 20:                       # compactar de vez en cuando: no copiar el búfer en cada mensaje
            del self.buf[:self.pos]
            self.pos = 0
        self.buf += chunk

    def _read_head(self):
        while True:
            i = self.buf.find(b"\r\n\r\n", self.pos)
            if i >= 0:
                head = bytes(self.buf[self.pos:i + 4])
                self.pos = i + 4
                return head
            if len(self.buf) - self.pos > 65536:
                raise WsError("cabecera HTTP demasiado larga")
            self._fill()

    def _exact(self, n):
        while len(self.buf) - self.pos < n:
            self._fill()
        out = bytes(self.buf[self.pos:self.pos + n])
        self.pos += n
        return out

    def recv(self):
        """(texto, hora de llegada) del siguiente mensaje de datos. Responde los ping; un cierre del servidor es un error."""
        parts = []
        while True:
            b1, b2 = self._exact(2)
            fin, op = b1 & 0x80, b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._exact(8))[0]
            mask = self._exact(4) if b2 & 0x80 else None
            data = self._exact(n)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 0x9:
                self._send(0xA, data)
                continue
            if op == 0xA:
                continue
            if op == 0x8:
                raise WsError("el servidor cerró el WebSocket")
            parts.append(data)
            if fin:
                return b"".join(parts).decode("utf-8", "replace"), self.wall()

    def recv_json(self):
        text, t = self.recv()
        return json.loads(text), t

    # -- envío (solo suscripciones) -----------------------------------------------------------
    def _send(self, op, payload):
        n = len(payload)
        head = bytearray([0x80 | op])
        if n < 126:
            head.append(0x80 | n)
        elif n < 65536:
            head.append(0x80 | 126)
            head += struct.pack(">H", n)
        else:
            head.append(0x80 | 127)
            head += struct.pack(">Q", n)
        mask = os.urandom(4)
        self.sock.sendall(bytes(head) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def call(self, req_id, method, params):
        """Manda una petición JSON-RPC. Solo se permiten suscripciones: este cliente no sirve para enviar nada a la cadena."""
        if method not in ALLOWED_METHODS:
            raise WsError(f"método no permitido por WebSocket: {method}")
        self._send(0x1, json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}).encode())

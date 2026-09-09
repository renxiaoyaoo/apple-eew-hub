from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import ssl
from types import TracebackType
from urllib.parse import urlparse


class SimpleWebSocket:
    def __init__(self, url: str, user_agent: str = "apple-eew-hub/0.1"):
        self.url = url
        self.user_agent = user_agent
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None

    async def __aenter__(self) -> "SimpleWebSocket":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    def __aiter__(self) -> "SimpleWebSocket":
        return self

    async def __anext__(self) -> str:
        message = await self.recv()
        if message is None:
            raise StopAsyncIteration
        return message

    async def connect(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme not in {"ws", "wss"}:
            raise ValueError(f"unsupported websocket scheme: {parsed.scheme}")
        host = parsed.hostname
        if not host:
            raise ValueError("websocket url missing host")
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        ssl_context = ssl.create_default_context() if parsed.scheme == "wss" else None
        try:
            self.reader, self.writer = await asyncio.open_connection(host, port, ssl=ssl_context, server_hostname=host if ssl_context else None)
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            host_header = host if parsed.port is None else f"{host}:{port}"
            request = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host_header}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "Accept-Encoding: identity\r\n"
                f"User-Agent: {self.user_agent}\r\n"
                "\r\n"
            )
            self.writer.write(request.encode("ascii"))
            await self.writer.drain()
            raw_headers = await self.reader.readuntil(b"\r\n\r\n")
            header_text = raw_headers.decode("iso-8859-1")
            lines = header_text.split("\r\n")
            status = lines[0].split(" ", 2)
            if len(status) < 2 or status[1] != "101":
                raise ConnectionError(lines[0])
            headers = {}
            for line in lines[1:]:
                if ":" in line:
                    name, value = line.split(":", 1)
                    headers[name.strip().lower()] = value.strip()
            expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()).decode("ascii")
            if headers.get("sec-websocket-accept") != expected:
                raise ConnectionError("invalid websocket accept key")
        except Exception:
            await self.close()
            raise

    async def recv(self) -> str | None:
        while True:
            reader = self._reader()
            try:
                first = await asyncio.wait_for(reader.readexactly(2), timeout=90)
            except TimeoutError:
                await self._send_frame(9, b"keepalive")
                first = await asyncio.wait_for(reader.readexactly(2), timeout=15)
            opcode = first[0] & 0x0F
            masked = bool(first[1] & 0x80)
            length = first[1] & 0x7F
            if length == 126:
                length = int.from_bytes(await reader.readexactly(2), "big")
            elif length == 127:
                length = int.from_bytes(await reader.readexactly(8), "big")
            if length > 8 * 1024 * 1024:
                raise ConnectionError("websocket frame exceeds 8 MiB")
            mask = await reader.readexactly(4) if masked else b""
            payload = await reader.readexactly(length) if length else b""
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 1:
                return payload.decode("utf-8")
            if opcode == 8:
                return None
            if opcode == 9:
                await self._send_frame(10, payload)

    async def close(self) -> None:
        if self.writer:
            try:
                await self._send_frame(8, b"")
            except Exception:
                pass
            self.writer.close()
            await self.writer.wait_closed()
            self.writer = None
            self.reader = None

    def _reader(self) -> asyncio.StreamReader:
        if not self.reader:
            raise ConnectionError("websocket is not connected")
        return self.reader

    def _writer(self) -> asyncio.StreamWriter:
        if not self.writer:
            raise ConnectionError("websocket is not connected")
        return self.writer

    async def _send_frame(self, opcode: int, payload: bytes) -> None:
        writer = self._writer()
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.extend([0x80 | 126])
            header.extend(length.to_bytes(2, "big"))
        else:
            header.extend([0x80 | 127])
            header.extend(length.to_bytes(8, "big"))
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        writer.write(bytes(header) + mask + masked)
        await writer.drain()

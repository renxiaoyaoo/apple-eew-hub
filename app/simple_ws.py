from __future__ import annotations

from types import TracebackType

from websockets.asyncio.client import ClientConnection
from websockets.asyncio.client import connect as websocket_connect
from websockets.exceptions import ConnectionClosedOK


class SimpleWebSocket:
    """Small adapter around websockets so listeners share one stable interface."""

    def __init__(self, url: str, user_agent: str = "apple-eew-hub/0.1"):
        self.url = url
        self.user_agent = user_agent
        self.connection: ClientConnection | None = None

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
        self.connection = await websocket_connect(
            self.url,
            user_agent_header=self.user_agent,
            open_timeout=15,
            ping_interval=30,
            ping_timeout=15,
            close_timeout=5,
            max_size=8 * 1024 * 1024,
        )

    async def recv(self) -> str | None:
        if not self.connection:
            raise ConnectionError("websocket is not connected")
        try:
            message = await self.connection.recv()
        except ConnectionClosedOK:
            return None
        if isinstance(message, bytes):
            return message.decode("utf-8")
        return message

    async def close(self) -> None:
        if self.connection:
            await self.connection.close()
            self.connection = None

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Awaitable, Callable

from gateway.config import NimResolvedConfig
from nim_bot_py.bridge import NimBridgeError as BridgeError
from nim_bot_py.bridge import NodeBridge


BridgeEventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


class NodeBridgeProcess(NodeBridge):
    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: str | None = None,
        request_timeout: float = 10.0,
    ) -> None:
        super().__init__(
            command=command,
            cwd=cwd,
            request_timeout=request_timeout,
            auto_install=True,
        )

    async def start(
        self,
        config: NimResolvedConfig,
        *,
        event_handler: BridgeEventHandler | None = None,
    ) -> None:
        await super().start(config, event_handler=event_handler)

    async def send_text(
        self,
        *,
        chat_id: str,
        text: str,
        session_type: str,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        return await self.send_message(
            chat_id=chat_id,
            text=text,
            session_type=session_type,
        )

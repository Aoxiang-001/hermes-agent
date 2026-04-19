from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Awaitable, Callable

from gateway.config import NimResolvedConfig
from gateway.platforms.nim_protocol import decode_jsonl_line, encode_jsonl


BridgeEventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


logger = logging.getLogger(__name__)


class BridgeError(RuntimeError):
    pass


class NodeBridgeProcess:
    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: str | None = None,
        request_timeout: float = 10.0,
    ) -> None:
        self._command = list(command)
        self._cwd = cwd or str(Path.cwd())
        self._request_timeout = request_timeout
        self._process: asyncio.subprocess.Process | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 0
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._event_handler: BridgeEventHandler | None = None
        self._event_tasks: set[asyncio.Task[Any]] = set()

    async def start(
        self,
        config: NimResolvedConfig,
        *,
        event_handler: BridgeEventHandler | None = None,
    ) -> None:
        if self._process is not None:
            return
        self._event_handler = event_handler
        self._process = await asyncio.create_subprocess_exec(
            *self._command,
            cwd=self._cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._stdout_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())
        response = await self.request("connect", {"config": config.to_bridge_payload()})
        if response.get("status") != "ok":
            raise BridgeError(response.get("error", "bridge connect failed"))

    async def stop(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            await self.request("disconnect", {})
        except Exception:
            pass
        if process.stdin is not None and not process.stdin.is_closing():
            process.stdin.close()
        await process.wait()
        for task in (self._stdout_task, self._stderr_task):
            if task is not None and not task.done():
                task.cancel()
        for task in list(self._event_tasks):
            if not task.done():
                task.cancel()
        self._process = None

    async def health(self) -> dict[str, Any]:
        response = await self.request("health", {})
        if response.get("status") != "ok":
            raise BridgeError(response.get("error", "bridge health failed"))
        return dict(response.get("result") or {})

    async def send_text(
        self,
        *,
        chat_id: str,
        text: str,
        session_type: str,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        response = await self.request(
            "send_message",
            {
                "chat_id": chat_id,
                "text": text,
                "session_type": session_type,
                "reply_to": reply_to,
            },
        )
        if response.get("status") != "ok":
            raise BridgeError(response.get("error", "send_message failed"))
        return dict(response.get("result") or {})

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        process = self._process
        if process is None or process.stdin is None:
            raise BridgeError("bridge process is not running")
        self._next_id += 1
        request_id = str(self._next_id)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[request_id] = future
        process.stdin.write(
            encode_jsonl(
                {
                    "id": request_id,
                    "type": "request",
                    "method": method,
                    "params": params,
                }
            )
        )
        await process.stdin.drain()
        try:
            return await asyncio.wait_for(future, timeout=self._request_timeout)
        finally:
            self._pending.pop(request_id, None)

    async def _read_stdout(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None
        while True:
            line = await self._process.stdout.readline()
            if not line:
                return
            message = decode_jsonl_line(line)
            await self._dispatch_stdout(message)

    async def _dispatch_stdout(self, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        if message_type == "response":
            request_id = str(message.get("id", ""))
            future = self._pending.get(request_id)
            if future is not None and not future.done():
                future.set_result(message)
            return
        if message_type == "event" and self._event_handler is not None:
            try:
                result = self._event_handler(message)
            except Exception:
                logger.exception("NIM bridge event handler failed")
                return
            if asyncio.iscoroutine(result):
                task = asyncio.create_task(result)
                self._event_tasks.add(task)
                task.add_done_callback(self._finalize_event_task)

    def _finalize_event_task(self, task: asyncio.Task[Any]) -> None:
        self._event_tasks.discard(task)
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("NIM bridge async event handler failed")

    async def _read_stderr(self) -> None:
        assert self._process is not None
        assert self._process.stderr is not None
        buffer = b""
        while True:
            chunk = await self._process.stderr.read(4096)
            if not chunk:
                if buffer:
                    sys.stderr.write(buffer.decode("utf-8", errors="replace"))
                return
            buffer += chunk
            while True:
                newline_index = buffer.find(b"\n")
                if newline_index < 0:
                    break
                line = buffer[: newline_index + 1]
                buffer = buffer[newline_index + 1 :]
                sys.stderr.write(line.decode("utf-8", errors="replace"))

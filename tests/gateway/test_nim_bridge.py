import asyncio
from types import SimpleNamespace

import pytest

from gateway.platforms.nim_bridge import BridgeError, NodeBridgeProcess


@pytest.mark.asyncio
async def test_dispatch_stdout_does_not_block_on_async_event_handler():
    gate = asyncio.Event()
    handled = asyncio.Event()

    async def event_handler(_message):
        handled.set()
        await gate.wait()

    bridge = NodeBridgeProcess(["node", "fake.mjs"])
    bridge._event_handler = event_handler

    loop = asyncio.get_running_loop()
    future = loop.create_future()
    bridge._pending["1"] = future

    await bridge._dispatch_stdout({"type": "event", "event": "message", "payload": {}})
    await asyncio.wait_for(handled.wait(), timeout=1)

    await bridge._dispatch_stdout({"type": "response", "id": "1", "status": "ok", "result": {"ok": True}})
    assert future.done() is True
    assert future.result()["result"] == {"ok": True}

    gate.set()
    await asyncio.gather(*bridge._event_tasks)


class _FakeStream:
    def __init__(self):
        self.closed = False

    async def readline(self):
        return b""

    async def read(self, _size):
        return b""

    def is_closing(self):
        return self.closed

    def close(self):
        self.closed = True


class _FakeProcess:
    def __init__(self):
        self.stdin = _FakeStream()
        self.stdout = _FakeStream()
        self.stderr = _FakeStream()
        self.returncode = None
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True
        self.returncode = 1

    def kill(self):
        self.killed = True
        self.returncode = 1

    async def wait(self):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


@pytest.mark.asyncio
async def test_start_cleans_up_subprocess_when_connect_fails(monkeypatch):
    process = _FakeProcess()

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return process

    async def fake_request(self, method, params):
        raise BridgeError("connect failed")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(NodeBridgeProcess, "request", fake_request)

    bridge = NodeBridgeProcess(["node", "fake.mjs"])
    config = SimpleNamespace(to_bridge_payload=lambda: {"credentials": {}})

    with pytest.raises(BridgeError, match="connect failed"):
        await bridge.start(config=config)

    assert process.terminated is True
    assert bridge._process is None

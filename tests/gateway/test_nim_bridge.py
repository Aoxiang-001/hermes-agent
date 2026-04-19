import asyncio

import pytest

from gateway.platforms.nim_bridge import NodeBridgeProcess


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

from __future__ import annotations

import json
from typing import Any


def encode_jsonl(message: dict[str, Any]) -> bytes:
    return (json.dumps(message, ensure_ascii=True) + "\n").encode("utf-8")


def decode_jsonl_line(line: bytes | str) -> dict[str, Any]:
    text = line.decode("utf-8").strip() if isinstance(line, bytes) else line.strip()
    if not text:
        raise ValueError("empty JSONL line")
    return json.loads(text)

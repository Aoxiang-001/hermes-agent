from __future__ import annotations

import logging
import os
import subprocess
import shutil
from pathlib import Path
from typing import Any, Optional

from gateway.config import (
    NimResolvedConfig,
    Platform,
    PlatformConfig,
    _default_nim_bridge_dir,
    _default_nim_bridge_command,
    load_nim_config,
)
from gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType, SendResult
from gateway.platforms.nim_bridge import NodeBridgeProcess

logger = logging.getLogger(__name__)


def _bundled_nim_sdk_dir(bridge_dir: Path) -> Path:
    return bridge_dir / "node_modules" / "@yxim" / "nim-bot"


def _ensure_bundled_nim_sdk(bridge_dir: Path) -> bool:
    bridge_script = bridge_dir / "index.mjs"
    package_json = bridge_dir / "package.json"
    sdk_dir = _bundled_nim_sdk_dir(bridge_dir)
    if not bridge_script.exists() or not package_json.exists():
        return False
    if sdk_dir.exists():
        return True

    npm = shutil.which("npm")
    if not npm:
        logger.warning("[nim] npm not found; cannot auto-install bundled @yxim/nim-bot")
        return False

    logger.info("[nim] Installing bundled @yxim/nim-bot dependency in %s", bridge_dir)
    try:
        result = subprocess.run(
            [npm, "install", "--no-fund", "--no-audit", "--prefix", str(bridge_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            logger.debug("[nim] npm install stdout: %s", result.stdout.strip())
        if result.stderr:
            logger.debug("[nim] npm install stderr: %s", result.stderr.strip())
    except (OSError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, subprocess.CalledProcessError):
            stderr = (exc.stderr or "").strip()
            logger.warning("[nim] Failed to auto-install @yxim/nim-bot: %s", stderr or exc)
        else:
            logger.warning("[nim] Failed to launch npm for bundled @yxim/nim-bot install: %s", exc)
        return False

    return sdk_dir.exists()


def check_nim_requirements(config: PlatformConfig | None = None) -> bool:
    resolved = load_nim_config(config or PlatformConfig(enabled=True))
    command = list(resolved.bridge_command or [])
    if not command:
        return False
    executable = command[0]
    if os.path.isabs(executable) or "/" in executable:
        executable_ok = Path(executable).exists()
    else:
        executable_ok = shutil.which(executable) is not None
    if not executable_ok:
        return False

    default_command = _default_nim_bridge_command()
    if command == default_command:
        bridge_dir = _default_nim_bridge_dir()
        bridge_script = bridge_dir / "index.mjs"
        if not bridge_script.exists():
            return False
        return _ensure_bundled_nim_sdk(bridge_dir)

    if len(command) >= 2 and executable.endswith("node"):
        return Path(command[1]).exists()

    return True


class NimAdapter(BasePlatformAdapter):
    MAX_MESSAGE_LENGTH = 4000

    def __init__(
        self,
        config: PlatformConfig,
        *,
        bridge: NodeBridgeProcess | Any | None = None,
    ) -> None:
        super().__init__(config=config, platform=Platform.NIM)
        self.resolved: NimResolvedConfig = load_nim_config(config)
        self._bridge = bridge or NodeBridgeProcess(self.resolved.bridge_command)
        self._chat_cache: dict[str, dict[str, str]] = {}

    async def connect(self) -> bool:
        if not self.resolved.configured():
            self._mark_disconnected()
            return False
        await self._bridge.start(self.resolved, event_handler=self._on_bridge_event)
        self._mark_connected()
        return True

    async def disconnect(self) -> None:
        await self._bridge.stop()
        self._mark_disconnected()

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SendResult:
        session_type = self._infer_session_type(chat_id, metadata)
        reply_to_id = reply_to or (metadata or {}).get("reply_to")
        result: dict[str, Any] | None = None
        for chunk in self._split_content(content):
            result = await self._bridge.send_text(
                chat_id=chat_id,
                text=chunk,
                session_type=session_type,
                reply_to=reply_to_id,
            )
        return SendResult(
            success=True,
            message_id=str((result or {}).get("message_id") or (result or {}).get("client_message_id") or ""),
            raw_response=result or {},
        )

    def _split_content(self, content: str) -> list[str]:
        if len(content) <= self.MAX_MESSAGE_LENGTH:
            return [content]

        chunks: list[str] = []
        remaining = content
        while remaining:
            if len(remaining) <= self.MAX_MESSAGE_LENGTH:
                chunks.append(remaining)
                break
            split_at = remaining.rfind("\n", 0, self.MAX_MESSAGE_LENGTH)
            if split_at > 0:
                chunks.append(remaining[:split_at + 1])
                remaining = remaining[split_at + 1 :]
                continue
            chunks.append(remaining[: self.MAX_MESSAGE_LENGTH])
            remaining = remaining[self.MAX_MESSAGE_LENGTH :]
        return chunks

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        cached = self._chat_cache.get(chat_id)
        if cached is not None:
            return dict(cached)
        if chat_id.startswith("team:"):
            return {"name": chat_id, "type": "group"}
        return {"name": chat_id, "type": "dm"}

    async def health(self) -> dict[str, Any]:
        return await self._bridge.health()

    async def _on_bridge_event(self, envelope: dict[str, Any]) -> None:
        if envelope.get("event") != "message":
            return
        payload = dict(envelope.get("payload") or {})
        if self._should_ignore(payload):
            return
        event = self._to_message_event(payload)
        self._chat_cache[event.source.chat_id] = {
            "name": event.source.chat_name or event.source.chat_id,
            "type": event.source.chat_type,
        }
        await self.handle_message(event)

    def _should_ignore(self, payload: dict[str, Any]) -> bool:
        if payload.get("from_self"):
            return True
        session_type = str(payload.get("session_type") or "p2p")
        sender_id = str(payload.get("sender_id") or "")
        if session_type == "p2p":
            return not self._is_allowed_direct_sender(sender_id)
        if session_type in {"team", "superTeam"}:
            if not self._is_allowed_group(str(payload.get("target_id") or "")):
                return True
            return not self._is_mentioned(payload)
        return True

    def _is_allowed_direct_sender(self, sender_id: str) -> bool:
        if self.resolved.allow_all_users:
            return True
        if not self.resolved.allowed_users:
            return True
        return sender_id in self.resolved.allowed_users

    def _is_allowed_group(self, target_id: str) -> bool:
        policy = self.resolved.group_policy
        if policy == "disabled":
            return False
        if policy == "open":
            return True
        return target_id in self.resolved.group_allowlist

    def _is_mentioned(self, payload: dict[str, Any]) -> bool:
        if payload.get("mentioned") or payload.get("mention_all"):
            return True
        force_push_ids = {str(item) for item in payload.get("force_push_account_ids") or []}
        account = self.resolved.credentials.account if self.resolved.credentials else ""
        return bool(account and account in force_push_ids)

    def _to_message_event(self, payload: dict[str, Any]) -> MessageEvent:
        session_type = str(payload.get("session_type") or "p2p")
        sender_id = str(payload.get("sender_id") or "")
        target_id = str(payload.get("target_id") or "")
        chat_type = "dm" if session_type == "p2p" else "group"
        chat_id = f"user:{sender_id}" if session_type == "p2p" else f"team:{target_id}"
        source = self.build_source(
            chat_id=chat_id,
            chat_type=chat_type,
            chat_name=payload.get("conversation_name"),
            user_id=sender_id,
            user_name=payload.get("sender_name"),
        )
        return MessageEvent(
            text=str(payload.get("text") or ""),
            message_type=self._to_message_type(str(payload.get("message_type") or "text")),
            source=source,
            raw_message=payload,
            message_id=str(payload.get("message_id") or payload.get("client_message_id") or ""),
            reply_to_message_id=str(payload.get("reply_to") or "") or None,
        )

    def _infer_session_type(self, chat_id: str, metadata: dict[str, Any] | None) -> str:
        if metadata and metadata.get("session_type"):
            return str(metadata["session_type"])
        if chat_id.startswith("team:"):
            return "team"
        return "p2p"

    def _to_message_type(self, value: str) -> MessageType:
        mapping = {
            "text": MessageType.TEXT,
            "image": MessageType.PHOTO,
            "audio": MessageType.AUDIO,
            "video": MessageType.VIDEO,
            "file": MessageType.DOCUMENT,
        }
        return mapping.get(value, MessageType.TEXT)


PlatformAdapter = NimAdapter

from unittest import mock

from gateway.config import (
    GatewayConfig,
    Platform,
    PlatformConfig,
    _default_nim_bridge_command,
    _resolve_nim_bridge_command,
    load_nim_config,
    parse_nim_token,
)


class TestParseNimToken:
    def test_pipe_separator(self):
        creds = parse_nim_token("app|bot|secret")
        assert creds is not None
        assert creds.app_key == "app"
        assert creds.account == "bot"
        assert creds.token == "secret"

    def test_dash_separator(self):
        creds = parse_nim_token("app-bot-secret")
        assert creds is not None
        assert creds.app_key == "app"
        assert creds.account == "bot"
        assert creds.token == "secret"


class TestLoadNimConfig:
    def test_loads_from_platform_token(self):
        resolved = load_nim_config(
            PlatformConfig(
                enabled=True,
                extra={
                    "nim_token": "from-token|bot|secret",
                    "bridge_command": "node /tmp/nim/index.mjs --stdio",
                },
            )
        )

        assert resolved.configured() is True
        assert resolved.credentials is not None
        assert resolved.credentials.app_key == "from-token"
        assert resolved.bridge_command == ["node", "/tmp/nim/index.mjs", "--stdio"]

    def test_loads_from_env_triplet(self):
        resolved = load_nim_config(
            PlatformConfig(enabled=True),
            {
                "NIM_APP_KEY": "app",
                "NIM_ACCOUNT": "bot",
                "NIM_TOKEN": "secret",
                "NIM_ALLOWED_USERS": "alice,bob",
                "NIM_GROUP_ALLOWLIST": "team-a,team-b",
                "NIM_GROUP_POLICY": "open",
                "NIM_ALLOW_ALL_USERS": "true",
            },
        )

        assert resolved.configured() is True
        assert resolved.allowed_users == ["alice", "bob"]
        assert resolved.group_allowlist == ["team-a", "team-b"]
        assert resolved.group_policy == "open"
        assert resolved.allow_all_users is True

    def test_default_bridge_command_uses_bundled_node_script(self):
        assert _resolve_nim_bridge_command(None) == _default_nim_bridge_command()
        assert _resolve_nim_bridge_command(None)[0] == "node"
        assert _resolve_nim_bridge_command(None)[1].endswith("gateway/platforms/nim_bridge_js/index.mjs")


class TestConnectedPlatforms:
    def test_nim_recognized_via_config_extra(self):
        config = GatewayConfig(
            platforms={
                Platform.NIM: PlatformConfig(
                    enabled=True,
                    extra={"nim_token": "app|bot|secret"},
                ),
            }
        )

        assert Platform.NIM in config.get_connected_platforms()

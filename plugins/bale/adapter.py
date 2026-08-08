"""
Bale (بله) platform adapter for Hermes Agent.

Bale uses a Telegram-compatible Bot API, so this adapter wraps the
built-in Telegram adapter and overrides the API base URL.
"""

import os
import types
import logging

logger = logging.getLogger(__name__)
BALE_BASE_URL = "https://tapi.bale.ai/bot"


def _is_connected(config) -> bool:
    """Bale is connected when BALE_BOT_TOKEN is configured."""
    token = getattr(config, "token", None)
    if not token:
        try:
            import hermes_cli.gateway as gateway_mod
            token = gateway_mod.get_env_value("BALE_BOT_TOKEN") or ""
        except Exception:
            token = os.environ.get("BALE_BOT_TOKEN", "")
    return bool(str(token).strip())


def _build_adapter(config):
    """Build a Telegram adapter configured for Bale API."""
    try:
        from plugins.platforms.telegram.adapter import _build_adapter as _tg_build
        from gateway.config import Platform

        # Ensure token is set from env
        bale_token = os.environ.get("BALE_BOT_TOKEN", "").strip()
        if bale_token and not getattr(config, "token", None):
            config.token = bale_token

        # Inject Bale base URL into config.extra
        extra = getattr(config, "extra", None) or {}
        if not isinstance(extra, dict):
            extra = {}
        extra["base_url"] = BALE_BASE_URL
        extra["base_file_url"] = BALE_BASE_URL
        config.extra = extra

        adapter = _tg_build(config)

        # ── Override platform ──────────────────────────────────────
        # build_source() uses self.platform for SessionSource, so this
        # alone fixes the routing: gateway looks up adapters[Platform("bale")]
        # instead of adapters[Platform.TELEGRAM].
        adapter.platform = Platform("bale")

        # ── Monkey-patch auth source builder ───────────────────────
        # _source_from_message_for_auth() hardcodes Platform.TELEGRAM
        # (line 1046 of the Telegram adapter).  The runner's
        # _is_user_authorized() reads source.platform to pick the
        # allowed-users env var.  If source.platform is TELEGRAM, it
        # checks TELEGRAM_ALLOWED_USERS — which doesn't include the
        # Bale user ID.  By stamping Platform("bale") on the auth
        # source, the runner checks BALE_ALLOWED_USERS instead.
        _orig_auth = adapter._source_from_message_for_auth

        def _bale_auth_source(self_adapter, message):
            source = _orig_auth(message)
            if source is not None:
                source.platform = Platform("bale")
            return source

        adapter._source_from_message_for_auth = types.MethodType(
            _bale_auth_source, adapter
        )

        logger.info("Bale adapter built (base_url=%s)", BALE_BASE_URL)
        return adapter
    except ImportError as e:
        raise RuntimeError(
            "Bale adapter requires the Telegram platform plugin. "
            "Make sure the telegram-platform plugin is installed."
        ) from e


async def _standalone_send(pconfig, chat_id, message, **kwargs):
    """Out-of-process Bale delivery via the Telegram standalone sender."""
    token = getattr(pconfig, "token", None)
    if not token:
        try:
            from agent.secret_scope import get_secret
            token = get_secret("BALE_BOT_TOKEN", "") or ""
        except Exception:
            token = os.environ.get("BALE_BOT_TOKEN", "")

    base_url = BALE_BASE_URL

    from tools.send_message_tool import _send_telegram
    import tools.send_message_tool as smt
    original_base = getattr(smt, "_TELEGRAM_BASE_URL", None)
    try:
        smt._TELEGRAM_BASE_URL = base_url
        return await _send_telegram(token, chat_id, message, **kwargs)
    finally:
        if original_base is not None:
            smt._TELEGRAM_BASE_URL = original_base
        elif hasattr(smt, "_TELEGRAM_BASE_URL"):
            delattr(smt, "_TELEGRAM_BASE_URL")


def register(ctx) -> None:
    """Plugin entry point — register Bale as a Telegram-compatible platform."""
    ctx.register_platform(
        name="bale",
        label="Bale",
        adapter_factory=_build_adapter,
        check_fn=lambda: True,
        is_connected=_is_connected,
        required_env=["BALE_BOT_TOKEN"],
        install_hint="Set BALE_BOT_TOKEN environment variable.",
        allowed_users_env="BALE_ALLOWED_USERS",
        allow_all_env="BALE_ALLOW_ALL_USERS",
        cron_deliver_env_var="BALE_HOME_CHANNEL",
        standalone_sender_fn=_standalone_send,
        max_message_length=4096,
        emoji="🟢",
        allow_update_command=True,
    )

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
BALE_FILE_URL = "https://tapi.bale.ai/file/bot"


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


def _check_bale_user(user_id: str) -> bool:
    """Check if a user_id is in BALE_ALLOWED_USERS."""
    if not user_id:
        return True

    allow_all = os.environ.get("BALE_ALLOW_ALL_USERS", "").strip().lower()
    if allow_all in ("true", "1", "yes"):
        return True

    allowed_csv = os.environ.get("BALE_ALLOWED_USERS", "").strip()
    if not allowed_csv:
        return True  # no allowlist → open

    allowed_ids = {uid.strip() for uid in allowed_csv.split(",") if uid.strip()}
    return "*" in allowed_ids or user_id in allowed_ids


def _bale_is_authorized(self, message) -> bool:
    """Check if sender is in BALE_ALLOWED_USERS (replaces Telegram's auth)."""
    user = getattr(message, "from_user", None)
    user_id = str(getattr(user, "id", "")).strip()
    return _check_bale_user(user_id)


def _build_adapter(config):
    """Build a Telegram adapter configured for Bale API."""
    try:
        from plugins.platforms.telegram.adapter import _build_adapter as _tg_build
        from gateway.config import Platform

        # Ensure token is set from env
        bale_token = os.environ.get("BALE_BOT_TOKEN", "").strip()
        if bale_token and not getattr(config, "token", None):
            config.token = bale_token

        # Inject Bale URLs into config.extra
        extra = getattr(config, "extra", None) or {}
        if not isinstance(extra, dict):
            extra = {}
        extra["base_url"] = BALE_BASE_URL
        extra["base_file_url"] = BALE_FILE_URL
        config.extra = extra

        adapter = _tg_build(config)

        # ── Fix 1: Override platform ──────────────────────────────
        adapter.platform = Platform("bale")

        # ── Fix 2: Override _is_user_authorized_from_message ─────
        adapter._is_user_authorized_from_message = types.MethodType(
            _bale_is_authorized, adapter
        )

        # ── Fix 3: Override _is_callback_user_authorized ──────────
        # This is used by terminal command approval (ea:choice:id).
        # Hardcodes Platform.TELEGRAM → runner checks TELEGRAM_ALLOWED_USERS.
        # Override to check BALE_ALLOWED_USERS directly.
        def _bale_callback_auth(self_adapter, user_id, **kwargs):
            return _check_bale_user(str(user_id).strip())

        adapter._is_callback_user_authorized = types.MethodType(
            _bale_callback_auth, adapter
        )

        # ── Fix 4: Stamp Platform("bale") on auth source ─────────
        _orig_auth_source = adapter._source_from_message_for_auth

        def _bale_auth_source(self_adapter, message):
            source = _orig_auth_source(message)
            if source is not None:
                source.platform = Platform("bale")
            return source

        adapter._source_from_message_for_auth = types.MethodType(
            _bale_auth_source, adapter
        )

        logger.info(
            "Bale adapter built (base_url=%s, file_url=%s)",
            BALE_BASE_URL, BALE_FILE_URL,
        )
        return adapter
    except Exception as e:
        logger.error("Bale adapter build failed: %s", e, exc_info=True)
        raise


async def _standalone_send(pconfig, chat_id, message, **kwargs):
    """Out-of-process Bale delivery via the Telegram standalone sender."""
    token = getattr(pconfig, "token", None)
    if not token:
        try:
            from agent.secret_scope import get_secret
            token = get_secret("BALE_BOT_TOKEN", "") or ""
        except Exception:
            token = os.environ.get("BALE_BOT_TOKEN", "")

    from tools.send_message_tool import _send_telegram
    import tools.send_message_tool as smt
    original_base = getattr(smt, "_TELEGRAM_BASE_URL", None)
    try:
        smt._TELEGRAM_BASE_URL = BALE_BASE_URL
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

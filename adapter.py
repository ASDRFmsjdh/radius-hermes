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


def _build_adapter(config):
    """Build a Telegram adapter configured for Bale API."""
    try:
        from plugins.platforms.telegram.adapter import _build_adapter as _tg_build
        from gateway.config import Platform
        from gateway.session import SessionSource

        bale_token = os.environ.get("BALE_BOT_TOKEN", "").strip()
        if bale_token and not getattr(config, "token", None):
            config.token = bale_token

        extra = getattr(config, "extra", None) or {}
        if not isinstance(extra, dict):
            extra = {}
        extra["base_url"] = BALE_BASE_URL
        extra["base_file_url"] = BALE_FILE_URL
        config.extra = extra

        adapter = _tg_build(config)
        adapter.platform = Platform("bale")

        # Patch auth source builder to stamp Platform("bale")
        _orig_auth = adapter._source_from_message_for_auth

        def _bale_auth_source(self_adapter, message):
            source = _orig_auth(message)
            if source is not None:
                source.platform = Platform("bale")
            return source

        adapter._source_from_message_for_auth = types.MethodType(
            _bale_auth_source, adapter
        )

        # Patch approval button auth to check BALE_ALLOWED_USERS
        def _bale_callback_auth(
            self_adapter, user_id, *, chat_id=None, chat_type=None,
            thread_id=None, user_name=None,
        ):
            normalized_user_id = str(user_id or "").strip()
            if not normalized_user_id:
                return False

            runner = getattr(
                getattr(self_adapter, "_message_handler", None), "__self__", None
            )
            auth_fn = getattr(runner, "_is_user_authorized", None)
            if callable(auth_fn):
                try:
                    ct = str(chat_type or "dm").strip().lower() or "dm"
                    if ct == "private":
                        ct = "dm"
                    elif ct == "supergroup":
                        ct = "forum" if thread_id is not None else "group"
                    source = SessionSource(
                        platform=Platform("bale"),
                        chat_id=str(chat_id or normalized_user_id),
                        chat_type=ct,
                        user_id=normalized_user_id,
                        user_name=str(user_name).strip() if user_name else None,
                        thread_id=str(thread_id) if thread_id is not None else None,
                    )
                    if bool(auth_fn(source)):
                        return True
                except Exception:
                    pass

            for env_key in ("BALE_ALLOWED_USERS", "TELEGRAM_ALLOWED_USERS"):
                csv = os.environ.get(env_key, "").strip()
                if csv:
                    ids = {u.strip() for u in csv.split(",") if u.strip()}
                    if "*" in ids or normalized_user_id in ids:
                        return True

            return os.environ.get("GATEWAY_ALLOW_ALL_USERS", "").lower() in {
                "true", "1", "yes",
            }

        adapter._is_callback_user_authorized = types.MethodType(
            _bale_callback_auth, adapter
        )

        logger.info("Bale adapter built (base_url=%s, file_url=%s)", BALE_BASE_URL, BALE_FILE_URL)
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
    """Plugin entry point."""
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

# Bale (بله) Platform Adapter for Hermes Agent

A plugin that adds [Bale (بله)](https://bale.ai) messaging platform support to Hermes Agent.

Bale uses a Telegram-compatible Bot API, so this adapter wraps the built-in Telegram adapter and overrides the API base URL to point to Bale's servers.

## Features

- ✅ Send and receive messages via Bale
- ✅ File upload/download support (images, documents, audio, video)
- ✅ Command approval via inline buttons
- ✅ Cron job delivery support
- ✅ Authorized users management (`BALE_ALLOWED_USERS`)

## Installation

1. Copy `adapter.py` and `plugin.yaml` to `~/.hermes/plugins/bale/`
2. Add your Bale bot token to `~/.hermes/.env`:
   ```
   BALE_BOT_TOKEN=your_bot_token_here
   BALE_ALLOWED_USERS=your_user_id_here
   ```
3. Restart Hermes gateway

## Configuration

| Variable | Description | Required |
|---|---|---|
| `BALE_BOT_TOKEN` | Bale Bot API token | Yes |
| `BALE_ALLOWED_USERS` | Comma-separated user IDs | No |
| `BALE_ALLOW_ALL_USERS` | Set to `true` to allow all users | No |
| `BALE_HOME_CHANNEL` | Home channel ID for cron delivery | No |

## How it works

The adapter:
1. Sets `platform` to `Platform("bale")` so the gateway routes responses correctly
2. Overrides `base_url` to `https://tapi.bale.ai/bot` for API calls
3. Overrides `base_file_url` to `https://tapi.bale.ai/file/bot` for file downloads
4. Monkey-patches `_source_from_message_for_auth` to stamp `Platform("bale")` for authorization
5. Monkey-patches `_is_callback_user_authorized` to check `BALE_ALLOWED_USERS`

## License

MIT

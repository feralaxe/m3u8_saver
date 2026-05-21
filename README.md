# m3u8_saver

Telegram bot backend that finds `.m3u8` playlists on a submitted page, lets an allowed user choose one, downloads/remuxes it to MP4 with ffmpeg, sends the file back, and deletes temporary files immediately afterwards.

## Features

- Telegram polling bot, suitable for Docker or an LXC VM.
- URL scanner for direct `.m3u8` links and playlists embedded in HTML.
- Inline buttons for choosing from found playlists.
- ffmpeg download and MP4 remux, with optional hardware-accelerated transcoding.
- Temporary per-download working folders removed in `finally`, even after failures.
- SQLite-backed subscriptions plus permanent allow-list users.
- Admin commands for granting or revoking subscription access.

## Quick start

1. Create a bot with BotFather and copy the token.
2. Copy `.env.example` to `.env`.
3. Set `TELEGRAM_BOT_TOKEN`, `ADMIN_USER_IDS`, and `PERMANENT_ALLOWED_USER_IDS`.
4. Run:

```bash
docker compose up --build -d
```

For local Python:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m m3u8_saver
```

On Windows PowerShell use `.venv\Scripts\Activate.ps1` instead of the Unix activate command.

Run tests with:

```bash
pip install -r requirements-dev.txt
PYTHONPATH=src pytest
```

## Access control

Permanent users are configured in `.env`:

```env
PERMANENT_ALLOWED_USER_IDS=123456789,987654321
```

Admins are also always allowed:

```env
ADMIN_USER_IDS=123456789
```

Users can send `/id` to get their Telegram user id.

Admin commands:

```text
/grantdays <user_id> <days>
/revoke <user_id>
/allowforever <user_id>
/unallowforever <user_id>
```

Subscription and runtime permanent-access data is stored in `DATA_DIR/bot.sqlite3`. Mount `./data:/app/data` in Docker if you want access records to survive container rebuilds.

## Video processing

Default behavior is stream-copy remuxing:

```env
TRANSCODE_VIDEO=false
```

This is usually fastest and does not need a GPU. ffmpeg reads the playlist segments, combines them, and writes an MP4 container.

If you need re-encoding, set:

```env
TRANSCODE_VIDEO=true
PREFERRED_ACCEL=auto
```

The bot will inspect available ffmpeg encoders and use NVIDIA NVENC, Intel QSV/VAAPI, AMD VAAPI/AMF, or software x264 as a fallback. For a future NVIDIA P1000/P2000 Docker setup, install NVIDIA Container Toolkit on the host and enable the NVIDIA device block in `docker-compose.yml`.

## Important limits

Telegram bot uploads have platform limits. Large videos may fail to upload even if ffmpeg produced them correctly. `MAX_VIDEO_BYTES` protects your server disk space before upload.

Some websites protect media URLs with cookies, DRM, expiring tokens, or JavaScript-only playback. This bot handles ordinary HTML-embedded and direct `.m3u8` URLs, but it does not bypass DRM or login restrictions.

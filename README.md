# m3u8_saver

Telegram bot backend that finds `.m3u8` playlists or supported YouTube videos from a submitted URL, lets an allowed user choose what to download, sends the file back, and deletes temporary files immediately afterwards.

## Features

- Telegram polling bot, suitable for Docker or an LXC VM.
- URL scanner for direct `.m3u8` links and playlists embedded in HTML.
- Inline buttons for choosing from found playlists.
- YouTube links with Best/Medium/Low quality buttons based on available source quality.
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

## Proxmox Docker setup

Recommended setup: run this bot in a small Debian or Ubuntu VM on Proxmox. A VM is simpler than LXC for Docker permissions and future GPU passthrough.

Suggested VM/LXC resources:

```text
CPU: 2 cores
RAM: 2-4 GB
Disk: 20+ GB
OS: Debian 12 or Ubuntu 24.04
Network: bridged to vmbr0
```

If you use an LXC container instead of a VM, enable nesting:

```text
Proxmox -> CT -> Options -> Features -> Nesting = enabled
```

Then reboot the container.

### 1. Fix/check networking

Inside the VM/LXC, check that networking works:

```bash
ip addr
ip route
ping -c 3 1.1.1.1
ping -c 3 deb.debian.org
```

If `ping -c 3 1.1.1.1` says `Network is unreachable`, fix the network device in Proxmox:

```text
Proxmox -> CT/VM -> Network
Name: eth0
Bridge: vmbr0
IPv4: DHCP
Gateway: DHCP
```

Or set a static address, for example:

```text
IPv4/CIDR: 192.168.1.104/24
Gateway: 192.168.1.1
DNS: 1.1.1.1 8.8.8.8
```

Use your router IP as the gateway. Restart the VM/LXC after changing network settings.

If `ping -c 3 1.1.1.1` works but `ping -c 3 deb.debian.org` fails, fix DNS:

```bash
cat > /etc/resolv.conf <<'EOF'
nameserver 1.1.1.1
nameserver 8.8.8.8
EOF
```

For a persistent DNS fix, set DNS in the Proxmox UI:

```text
Proxmox -> CT/VM -> DNS
DNS servers: 1.1.1.1 8.8.8.8
DNS domain: local
```

### 2. Install Docker

Most Proxmox Debian containers log in as `root`, so `sudo` may not exist. Run these commands as `root`:

```bash
apt update
apt install -y curl ca-certificates git
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker
```

Check Docker:

```bash
docker --version
docker compose version
```

If `docker compose version` fails:

```bash
apt install -y docker-compose-plugin
```

### 3. Put the bot on the server

Clone the repo:

```bash
cd /opt
git clone <your-repo-url> m3u8_saver
cd /opt/m3u8_saver
```

Or copy the project folder manually to:

```text
/opt/m3u8_saver
```

### 4. Configure the bot

Create `.env`:

```bash
cp .env.example .env
nano .env
```

Set at least:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
ADMIN_USER_IDS=your_telegram_user_id
PERMANENT_ALLOWED_USER_IDS=your_telegram_user_id
DATA_DIR=/app/data
TEMP_DIR=/tmp/m3u8-saver
TRANSCODE_VIDEO=false
PREFERRED_ACCEL=auto
LOG_LEVEL=INFO
LOG_FILE=/app/data/bot.log
```

You can get your Telegram user id by messaging the bot with `/id` after it starts, or by using a Telegram user-info bot.

### 5. Start the bot

From `/opt/m3u8_saver`:

```bash
docker compose up --build -d
```

Check that it is running:

```bash
docker compose ps
docker compose logs -f bot
```

In Telegram, send:

```text
/start
/id
```

Then send a page URL or direct `.m3u8` URL.

For YouTube, send a normal YouTube URL. The bot checks available formats first and then shows quality buttons:

```text
Best: highest source quality, shown only if the source is above 720p
Medium: up to 720p, shown when a 720p-level source exists
Low: up to 480p
```

If the best available source is 720p, the bot hides `Best`. If the best available source is 480p or lower, it shows only `Low`.

### 6. Manage access

Allow a user permanently:

```text
/allowforever 123456789
```

Grant temporary access:

```text
/grantdays 123456789 30
```

Revoke temporary subscription:

```text
/revoke 123456789
```

Remove runtime permanent access:

```text
/unallowforever 123456789
```

Access data is stored on the host in:

```text
/opt/m3u8_saver/data/bot.sqlite3
```

### 7. Read logs

Live Docker logs:

```bash
cd /opt/m3u8_saver
docker compose logs -f bot
```

Saved rotating log file:

```bash
tail -f /opt/m3u8_saver/data/bot.log
```

Show the last 200 lines:

```bash
tail -n 200 /opt/m3u8_saver/data/bot.log
```

### HTTP 498 from Wildberries/Wibes

If logs show something like:

```text
Source site rejected the request with HTTP 498
```

the source website rejected the bot before the page could be parsed. Wildberries/Wibes may require a real browser session, region/IP checks, or a temporary token. This is not an ffmpeg error; it happens before the bot finds any `.m3u8` URL.

Try these in order:

1. Open the page in your browser, use Developer Tools -> Network, filter for `m3u8`, and send the direct `.m3u8` URL to the bot.
2. If the media requires your own logged-in browser session, copy only the needed cookie values from your browser and set them in `.env`:

```env
SOURCE_COOKIE=sessionid=abc; other_cookie=xyz
```

Then restart:

```bash
docker compose up -d
```

3. If the site still returns `498`, the server is blocking the container IP/client. The bot cannot parse that page unless the source site allows server-side access to the page or playlist.

Do not put cookies from accounts you do not own into the bot. Cookies are sensitive secrets; keep `.env` private.

### 8. Update later

```bash
cd /opt/m3u8_saver
git pull
docker compose up --build -d
docker compose logs -f bot
```

Use `--build` after updates that change Python dependencies, such as the YouTube support added through `yt-dlp`.

### 9. Future GPU notes

Keep this for now:

```env
TRANSCODE_VIDEO=false
```

That uses ffmpeg stream-copy remuxing, which is usually fastest and does not need a GPU.

When you add an NVIDIA Quadro P1000/P2000, install the NVIDIA driver and NVIDIA Container Toolkit for your VM/container setup, then enable the NVIDIA device block in `docker-compose.yml` and set:

```env
TRANSCODE_VIDEO=true
PREFERRED_ACCEL=nvidia
```

For Intel or AMD VAAPI, pass `/dev/dri` into the container using the commented `devices` section in `docker-compose.yml`.

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

## Logging

Logs are written to Docker stdout and, if `LOG_FILE` is set, to a rotating file.

Default `.env` logging:

```env
LOG_LEVEL=INFO
LOG_FILE=/app/data/bot.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5
```

Read live Docker logs:

```bash
docker compose logs -f bot
```

Read the saved log file on the host:

```bash
tail -f ./data/bot.log
```

Show the last 200 lines:

```bash
tail -n 200 ./data/bot.log
```

Increase detail temporarily by setting this in `.env` and restarting:

```env
LOG_LEVEL=DEBUG
```

Then restart:

```bash
docker compose up -d
```

Log files rotate automatically:

```text
data/bot.log
data/bot.log.1
data/bot.log.2
```

The bot logs startup, access decisions, URL discovery, download start/end, upload start/end, ffmpeg failures, unexpected errors, and cleanup. Query strings are removed from logged URLs to avoid storing tokens in logs.

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

## YouTube

YouTube support uses `yt-dlp` to inspect and download formats. ffmpeg is still used inside the container to merge separate video and audio tracks into MP4.

Send a YouTube URL to the bot. If the video can be inspected, the bot replies with quality buttons:

```text
Best
Medium (720p)
Low (480p)
```

The buttons depend on the available source formats:

```text
1080p or higher source: Best, Medium, Low
720p maximum source: Medium, Low
480p or lower maximum source: Low only
```

Optional YouTube cookies can be set in `.env` if YouTube requires your own browser session:

```env
YOUTUBE_COOKIE=session_cookie=value; another_cookie=value
```

Keep cookies private. Only download videos you own, videos licensed for download, or videos you otherwise have permission to download.

## Important limits

Telegram bot uploads have platform limits. Large videos may fail to upload even if ffmpeg produced them correctly. `MAX_VIDEO_BYTES` protects your server disk space before upload.

Some websites protect media URLs with cookies, DRM, expiring tokens, or JavaScript-only playback. This bot handles ordinary HTML-embedded `.m3u8` URLs, direct `.m3u8` URLs, and supported YouTube URLs, but it does not bypass DRM or login restrictions.

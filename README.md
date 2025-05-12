![Project Preview](https://github.com/2boom-ua/watchdigest/blob/main/screenshot.png?raw=true)
<div align="center">  
    <img src="https://github.com/2boom-ua/watchdigest/blob/main/screenshot.png?raw=true" alt="" width="821" height="423">
</div>

## Monitor Docker images for outdated digests and send notifications to various platforms when updates are available.

WatchDigest is a Python-based monitoring tool that scans local Docker containers, checks whether their images are outdated, and optionally updates those images. It can notify you across a wide range of messaging platforms when updates are available or have been applied.

### Features:
Supports multiple container registries (docker.io, ghcr.io, lscr.io, registry.gitlab.com, etc.).
Automated digest checking to detect outdated images.
Optionally auto-update outdated Docker images and restart containers.
Webhook-based notifications (supports multiple messaging platforms).
Configurable polling period via config.json.
Docker API integration to retrieve local image data.

- **Real-time notifications with support for multiple accounts** via:
  - Telegram
  - Discord
  - Slack
  - Gotify
  - Ntfy
  - Pushbullet
  - Pushover
  - Rocket.chat
  - Matrix
  - Mattermost
  - Zulip
  - Pumble
  - Flock
  - Apprise
  - Webntfy
  - Custom

- **Customizable polling interval** through a configuration file (`config.json`).

### Requirements

- Python 3.X or higher
- Docker installed and running
- Dependencies: `docker`, `requests`, `schedule`, `Flask`
---

### Edit config.json:
You can use any name and any number of records for each messaging platform configuration, and you can also mix platforms as needed. The number of message platform configurations is unlimited.

[Configuration examples for Telegram, Matrix, Apprise, Pumble, Mattermost, Discord, Ntfy, Gotify, Zulip, Flock, Slack, Rocket.Chat, Pushover, Pushbullet](docs/json_message_config.md)
```
    "CUSTOM_NAME": {
        "ENABLED": false,
        "WEBHOOK_URL": [
            "first url",
            "second url",
            "...."
        ],
        "HEADER": [
            {first JSON structure},
            {second JSON structure},
            {....}
        ],
        "PAYLOAD": [
            {first JSON structure},
            {second JSON structure},
            {....}
        ],
        "FORMAT_MESSAGE": [
            "markdown",
            "html",
            "...."
        ]
    },
```
| Item | Required | Description |
|------------|------------|------------|
| ENABLED | true/false | Enable or disable Custom notifications |
| WEBHOOK_URL | url | The URL of your Custom webhook |
| HEADER | JSON structure | HTTP headers for each webhook request. This varies per service and may include fields like {"Content-Type": "application/json"}. |
| PAYLOAD | JSON structure | The JSON payload structure for each service, which usually includes message content and format. Like as  {"body": "message", "type": "info", "format": "markdown"}|
| FORMAT_MESSAGE | markdown,<br>html,<br>text,<br>simplified | Specifies the message format used by each service, such as markdown, html, or other text formatting.|

- **markdown** - a text-based format with lightweight syntax for basic styling (Pumble, Mattermost, Discord, Ntfy, Gotify),
- **simplified** - simplified standard Markdown (Telegram, Zulip, Flock, Slack, RocketChat).
- **html** - a web-based format using tags for advanced text styling,
- **text** - raw text without any styling or formatting.

```
    "STARTUP_MESSAGE": false,
    "NOTIFY_ENABLED": true,
    "UPGRADE_MODE": true,
    "START_TIMES": ["06:00", "14:00", "22:00"],
    "COMPOSE_FILES": ["compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml"]
    "DEFAULT_DOT_STYLE": true,
```
| Item   | Required   | Description   |
|------------|------------|------------|
| STARTUP_MESSAGE | true/false | On/Off startup message. | 
| NOTIFY_ENABLED | true/false | On/Off notification via messaging platforms. | 
| UPGRADE_MODE       | true/false   | Automatically pull and restart containers with updated images if enabled.  |
| START_TIMES        | list[string] | Specific times (24h format) to run the script if scheduled.                 |
| COMPOSE_FILES      | list[string] | Compose filenames to detect and use when recreating containers.            |
| DEFAULT_DOT_STYLE | true/false | Round/Square dots. |
---

### Clone the repository:
```
git clone https://github.com/2boom-ua/watchdigest.git
cd watchdigest
```
---
## Docker
```bash
  touch data.db
```
```bash
  docker build -t watchdigest .
```
or
```bash
  docker pull ghcr.io/2boom-ua/watchdigest:latest
```
### Dowload and edit config.json
```bash
curl -L -o ./config.json  https://raw.githubusercontent.com/2boom-ua/watchdigest/main/config.json
```
### docker-cli
```bash
docker run --name watchdigest -p 5151:5151 -v ./config.json:/watchdigest/config.json -v ./data.db:/watchdigest/data.db -v /var/run/docker.sock:/var/run/docker.sock -e TZ=Etc/UTC --restart always ghcr.io/2boom-ua/watchdigest:latest 
```
### docker-compose
```
services:
  watchdigest:
    image: ghcr.io/2boom-ua/watchdigest:latest
    container_name: watchdigest
    ports:
      - 5151:5151
    volumes:
      - ./config.json:/watchdigest/config.json
      - ./data.db:/watchdigest/data.db
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - TZ=Etc/UTC
    restart: always
```

```bash
docker-compose up -d
```
---

## Running as a Linux Service
You can set this script to run as a Linux service for continuous monitoring.

### Install required Python packages:

```
pip install -r requirements.txt
```

Create a systemd service file:
```
nano /etc/systemd/system/watchdigest.service
```
Add the following content:

```
[Unit]
Description=check docker update status
After=multi-user.target

[Service]
Type=simple
Restart=always
ExecStart=/usr/bin/python3 /opt/watchdigest/watchdigest.py

[Install]
WantedBy=multi-user.target
```
Start and enable the service:

```
systemctl daemon-reload
```
```
systemctl enable watchdigest.service
```
```
systemctl start watchdigest.service
```
### View

**https://your_domain_name or http://server_ip:5151**

### License

This project is licensed under the MIT License - see the [MIT License](https://opensource.org/licenses/MIT) for details.

### Author

- **2boom** - [GitHub](https://github.com/2boom-ua)


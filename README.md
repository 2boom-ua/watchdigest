
<div align="center">  
    <img src="https://github.com/2boom-ua/watchdigest/blob/main/screenshot.png?raw=true" alt="" width="800" height="268">
</div>

*The idea for this software was inspired by* [containrrr/watchtower]([https://github.com/petersem/monocker](https://github.com/containrrr/watchtower))


## WatchDigest

**WatchDigest** is a lightweight Python-based tool that monitors your Docker containers for outdated image digests and optionally updates them. It can notify you across various messaging platforms when updates are available or have been applied.

### Features
- Scans local Docker containers and checks if images are outdated
- Compares image digests with those from registries like Docker Hub, GitHub Container Registry, GitLab, etc.
- Optionally pulls and upgrades containers with the latest image
- Sends notifications to:
  - Telegram, Discord, Gotify, Ntfy
  - Pushbullet, Pushover, Slack
  - Matrix, Mattermost, Pumble
  - Rocket.Chat, Zulip, Flock, Custom
  - Any Apprise-compatible endpoint
  - Includes a simple web interface (Flask) to view container status and logs
  - Configurable check and update schedule
  - Designed to run as a Linux service or Docker container.

- **Customizable polling interval** through a configuration file (`config.json`).

### Requirements
- Python 3.X or higher
- Docker installed and running
- Dependencies: `docker`, `requests`, `schedule`, `Flask`

### View
**https://your_domain_name or http://server_ip:5151**

---
### Config Notification
Easily configure your settings with the [Multi-Platform Notification JSON Creator.](https://github.com/2boom-ua/mpn_json)

### Edit config.json:
You can use any name and any number of records for each messaging platform configuration, and you can also mix platforms as needed. The number of message platform configurations is unlimited.

[Configuration examples for Telegram, Matrix, Apprise, Pumble, Mattermost, Discord, Ntfy, Gotify, Zulip, Flock, Slack, Rocket.Chat, Pushover, Pushbullet, Webntfy](docs/json_message_config.md)
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
    restart: unless-stopped
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
### License
This project is licensed under the MIT License - see the [MIT License](https://opensource.org/licenses/MIT) for details.

### Author
- **2boom** - [GitHub](https://github.com/2boom-ua)


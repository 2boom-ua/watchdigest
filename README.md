## Docker monitoring tool that tracks Docker image updates

WatchDigest is a Python-based monitoring tool that tracks Docker image updates by comparing local digests with remote registries (Docker Hub, GitHub Container Registry, GitLab and others). It periodically checks for outdated images and sends notifications via webhooks.

### Features:
Supports multiple container registries (docker.io, ghcr.io, registry.gitlab.com, etc.).
Automated digest checking to detect outdated images.
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
- Dependencies: `docker`, `requests`, `schedule`
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
        "PYLOAD": [
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
    "STARTUP_MESSAGE": true,
    "DEFAULT_DOT_STYLE": true,
    "GHCR_PAT": "your_personal_access_token",
    "HOUR_REPEAT": 2
```
| Item   | Required   | Description   |
|------------|------------|------------|
| STARTUP_MESSAGE | true/false | On/Off startup message. | 
| DEFAULT_DOT_STYLE | true/false | Round/Square dots. |
| GHCR_PAT | string/empty string | **Optional:** GHCR_PAT (GitHub Container Registry Personal Access Token) is a scoped authentication token used to access GitHub's container registry (ghcr.io).  |
| HOUR_REPEAT | 2 | Set the poll period in hours. Minimum is 1 hour. | 
---
### How to Get a GitHub Container Registry (GHCR) Personal Access Token (PAT)
#### Generate a Personal Access Token (PAT)
1. Go to [GitHub Personal Access Tokens](https://github.com/settings/tokens).
2. Click **"Generate new token (classic)"**.
3. Set a **name** and **expiration date**.
4. Select the following **scopes**:
   - `read:packages` → **Pull images**
   - `write:packages` → **Push images**
   - `delete:packages` (optional) → **Delete images**
   - `repo` (if working with private repositories)
5. Click **"Generate token"** and **save** it securely.

#### Authenticate with GHCR
Run the following command in your terminal:
```sh
echo YOUR_PAT | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```
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
docker run -v ./config.json:/watchdigest/config.json -v /var/run/docker.sock:/var/run/docker.sock --name watchdigest -e TZ=UTC ghcr.io/2boom-ua/watchdigest:latest 
```
### docker-compose
```
version: "3.8"
services:
  watchdigest:
    image: ghcr.io/2boom-ua/watchdigest:latest
    container_name: watchdigest
    volumes:
      - ./config.json:/watchdigest/config.json
      - ./data.db:/watchdigest/data.db
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - TZ=UTC
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

### License

This project is licensed under the MIT License - see the [MIT License](https://opensource.org/licenses/MIT) for details.

### Author

- **2boom** - [GitHub](https://github.com/2boom-ua)


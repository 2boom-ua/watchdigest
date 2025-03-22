#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2025 2boom.

import json
import docker
import os
import sys
import time
import requests
import socket
import logging
import random
import platform
import threading
from schedule import every, repeat, run_pending
from docker.errors import DockerException
from urllib.parse import urlparse
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request


"""Configure logging"""
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.disabled = True

app = Flask(__name__)

docker_image_data = []
next_run_time = "Not yet scheduled"
last_checked_time = "Not yet checked"


def cutMessageUrl(url):
    """Truncate URL for logging brevity."""
    parsed_url = urlparse(url)
    return f"{parsed_url.scheme}://{parsed_url.netloc}...."


def getPlatformBaseUrl() -> str:
    """Return Docker socket path based on OS."""
    return 'unix://var/run/docker.sock' if platform.system() == "Linux" else 'npipe:////./pipe/docker_engine'


def getDockerInfo() -> dict:
    """Fetch Docker node name and version."""
    try:
        docker_client = docker.DockerClient(base_url=platform_base_url)
        return {
            "docker_engine_name": docker_client.info().get("Name", ""),
            "docker_version": docker_client.version().get("Version", "")
        }
    except (DockerException, Exception) as e:
        logger.error(f"Error fetching Docker info: {e}")
        return {"docker_engine_name": "", "docker_version": ""}


def SendMessage(message: str):
    """Send HTTP POST requests with retry logic."""
    def SendRequest(url, json_data=None, data=None, headers=None):
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                response = requests.post(url, json=json_data, data=data, headers=headers, timeout=(5, 20))
                response.raise_for_status()
                return
            except requests.exceptions.RequestException as e:
                logger.error(f"Attempt {attempt + 1}/{max_attempts} - Error sending to {cutMessageUrl(url)}: {e}")
                if attempt == max_attempts - 1:
                    logger.error(f"Failed to send to {cutMessageUrl(url)} after {max_attempts} attempts")
                else:
                    backoff_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Retrying in {backoff_time:.2f} seconds...")
                    time.sleep(backoff_time)

    def toHTMLFormat(message: str) -> str:
        """Convert message to HTML bold format."""
        message = ''.join(f"<b>{part}</b>" if i % 2 else part for i, part in enumerate(message.split('*')))
        return message.replace("\n", "<br>")

    def toMarkdownFormat(message: str, markdown_type: str) -> str:
        """Format message based on specified type."""
        if markdown_type == "html":
            return toHTMLFormat(message)
        elif markdown_type == "markdown":
            return message.replace("*", "**")
        elif markdown_type == "text":
            return message.replace("*", "")
        elif markdown_type == "simplified":
            return message
        else:
            logger.error(f"Unknown format '{markdown_type}'. Returning original message.")
            return message

    for url, header, payload, format_message in zip(platform_webhook_url, platform_header, platform_payload, platform_format_message):
        data, ntfy = None, False
        formatted_message = toMarkdownFormat(message, format_message)
        header_json = header if header else None
        for key in list(payload.keys()):
            if key == "title":
                delimiter = "<br>" if format_message == "html" else "\n"
                header, formatted_message = formatted_message.split(delimiter, 1)
                payload[key] = header.replace("*", "")
            elif key == "extras":
                formatted_message = formatted_message.replace("\n", "\n\n")
                payload["message"] = formatted_message
            elif key == "data":
                ntfy = True
            payload[key] = formatted_message if key in ["text", "content", "message", "body", "formatted_body", "data"] else payload[key]
        payload_json = None if ntfy else payload
        data = formatted_message.encode("utf-8") if ntfy else None
        SendRequest(url, payload_json, data, header_json)


def getDockerData() -> list:
    """Retrieve Docker image data including container name, size, and formatted creation date."""
    global docker_image_data
    resource_data = []
    try:
        docker_client = docker.DockerClient(base_url=platform_base_url, version="auto")
        images = docker_client.images.list(filters={'dangling': False})
        all_containers = docker_client.containers.list(all=True)
        used_image_ids = {}
        for container in all_containers:
            image_id = container.attrs['Image']
            if image_id.startswith('sha256:'):
                image_id = image_id[7:]
            container_name = container.attrs['Name'].lstrip('/')
            if image_id in used_image_ids:
                used_image_ids[image_id].append(container_name)
            else:
                used_image_ids[image_id] = [container_name]
        for image in images:
            if not image.tags:
                continue
            short_id = image.id[7:] if image.id.startswith('sha256:') else image.id
            if short_id in used_image_ids:
                image_source = image_owner = image_name = image_tag = ""
                fullname, image_tag = image.tags[0].rsplit(":", 1) if ":" in image.tags[0] else (image.tags[0], "latest")
                parts = fullname.split("/")
                if fullname.startswith(("ghcr.io", "registry.gitlab.com")):
                    image_source = parts[0]
                    image_owner = parts[1]
                    image_name = "/".join(parts[2:]) if len(parts) > 2 else parts[1]
                elif fullname.startswith("registry.") and not fullname.startswith("registry.gitlab.com"):
                    image_source = parts[0]
                    image_owner = parts[1]
                    image_name = "/".join(parts[2:]) if len(parts) > 2 else parts[1]
                elif parts[0] in ["library", "postgres"]:
                    image_source = "registry.hub.docker.com"
                    image_owner, image_name = parts if len(parts) > 1 else ("library", parts[0])
                elif len(parts) == 2:
                    image_source = "docker.io"
                    image_owner, image_name = parts
                else:
                    image_source = "local"
                    image_owner = "local"
                    image_name = fullname
                repo_digests = image.attrs.get("RepoDigests", [])
                digest = repo_digests[0].split("@")[1] if repo_digests else "NoDigest"
                size_mb = image.attrs.get("Size", 0) / (1024 * 1024)
                created_raw = image.attrs.get("Created", None)
                logger.debug(f"Raw Created value for {fullname}:{image_tag}: {created_raw}")
                if created_raw:
                    try:
                        if '.' in created_raw:
                            base, frac = created_raw.split('.')
                            frac = frac.rstrip('Z')
                            frac = frac[:6] + 'Z' if frac else '000000Z'
                            created_raw_truncated = f"{base}.{frac}"
                        else:
                            created_raw_truncated = created_raw
                        created_dt = datetime.strptime(created_raw_truncated, "%Y-%m-%dT%H:%M:%S.%fZ")
                        created = created_dt.strftime("%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        try:
                            created_dt = datetime.strptime(created_raw, "%Y-%m-%dT%H:%M:%SZ")
                            created = created_dt.strftime("%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            logger.error(f"Failed to parse Created timestamp: {created_raw}")
                            created = "Unknown"
                    except Exception as e:
                        logger.error(f"Unexpected error parsing timestamp: {e}")
                        created = "Unknown"
                else:
                    logger.warning(f"No Created timestamp found for {fullname}:{image_tag}")
                    created = "Unknown"
                container_names = ", ".join(used_image_ids[short_id])
                resource_data.append({
                    "container_name": container_names,
                    "digest": digest,
                    "image": f"{image_source}/{image_owner}/{image_name}:{image_tag}",
                    "size": f"{size_mb:.2f} MB",
                    "status": "unknown",
                    "created": created
                })
        docker_image_data = resource_data
    except (DockerException, Exception) as e:
        logger.error(f"Error retrieving Docker data: {e}")
    return resource_data


def getDockerDigest(registry: str, owner: str, image: str, tag: str) -> str:
    """Retrieve the latest digest for a Docker image from a registry."""
    digest = ""
    max_retries, retry_delay = 3, 2
    if registry == "ghcr.io":
        auth_url = f"https://ghcr.io/token?scope=repository:{owner}/{image}:pull"
        manifest_url = f"https://ghcr.io/v2/{owner}/{image}/manifests/{tag}"
    elif registry in ["docker.io", "registry.hub.docker.com"]:
        auth_url = "https://auth.docker.io/token"
        auth_params = {"service": "registry.docker.io", "scope": f"repository:{owner}/{image}:pull"}
        manifest_url = f"https://registry-1.docker.io/v2/{owner}/{image}/manifests/{tag}"
    elif registry == "registry.gitlab.com":
        auth_url = f"https://gitlab.com/jwt/auth?service=container_registry&scope=repository:{owner}/{image}:pull"
        manifest_url = f"https://registry.gitlab.com/v2/{owner}/{image}/manifests/{tag}"
    else:
        auth_url = f"https://{registry}/v2/token"
        manifest_url = f"https://{registry}/v2/{owner}/{image}/manifests/{tag}"
    try:
        response_token = requests.get(auth_url, params=auth_params if registry in ["docker.io", "registry.hub.docker.com"] else None)
        if response_token.status_code == 200:
            token = response_token.json().get("token", "")
        else:
            return digest
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": ", ".join([
                "application/vnd.docker.distribution.manifest.v2+json",
                "application/vnd.docker.distribution.manifest.list.v2+json",
                "application/vnd.oci.image.manifest.v1+json",
                "application/vnd.oci.image.index.v1+json",
            ])
        }
        for attempt in range(max_retries):
            response = requests.get(manifest_url, headers=headers)
            if response.status_code == 200:
                digest = response.headers.get("Docker-Content-Digest", "")
                if digest:
                    return digest
                else:
                    manifest_data = response.json()
                    if "manifests" in manifest_data:
                        for manifest in manifest_data["manifests"]:
                            if manifest.get("mediaType") in [
                                "application/vnd.docker.distribution.manifest.v2+json",
                                "application/vnd.oci.image.manifest.v1+json"
                            ]:
                                return manifest["digest"]
            elif response.status_code == 404:
                return digest
            else:
                time.sleep(retry_delay)
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {e}")
    return digest


def watchDigest():
    """Check for outdated Docker images by comparing local and remote digests."""
    global old_list, docker_image_data, next_run_time, last_checked_time
    new_list = result = []
    time_start = datetime.now()
    count_all = count_with_digest = 0
    for data in getDockerData():
        local_digest = data["digest"]
        full_image = data["image"]
        source, rest = full_image.split("/", 1)
        owner_image, tag = rest.rsplit(":", 1)
        owner, image = owner_image.split("/", 1) if "/" in owner_image else ("library", owner_image)
        if source.startswith(("docker.io", "ghcr.io", "registry.gitlab.com", "registry.")):
            digest = getDockerDigest(source, owner, image, tag)
            if digest:
                count_with_digest += 1
            for item in docker_image_data:
                if item["image"] != full_image:
                    continue

                if digest and digest != local_digest:
                    item["status"] = "outdated"
                    new_list.append(f"{orange_dot} *{owner}/{image}:{tag}* outdated!\n")
                elif digest:
                    item["status"] = "uptodate"
                else:
                    item["status"] = "error"
        else:
            for item in docker_image_data:
                if item["image"] != full_image:
                    continue
            
                if local_digest == "NoDigest":
                    item["status"] = "nodigest"
                elif source.startswith("local"):
                    item["status"] = "uptodate"
                else:
                    item["status"] = "error"
        count_all += 1
    if new_list:
        if len(new_list) >= len(old_list):
            result = [item for item in new_list if item not in old_list]
    old_list = new_list
    with open(file_db, "w") as file:
        file.writelines(old_list)
    time_end = datetime.now()
    elapsed = time_end - time_start
    minutes, seconds = divmod(elapsed.total_seconds(), 60)
    logger.info(f"Process complete! Execution time: {int(minutes):02d}:{int(seconds):02d}")
    logger.info(f"{count_all} local digests tracked, {count_with_digest} completed.")
    if result:
        SendMessage(f"{header_message}{''.join(result)}")
        logger.info(f"{''.join(result).replace(orange_dot, '').replace('*', '').strip()}")
    last_checked_time = time_end.strftime('%Y-%m-%d %H:%M:%S')
    next_run_time = (time_end + timedelta(minutes=min_repeat)).strftime('%Y-%m-%d %H:%M:%S')
    logger.info(f"Next run: {next_run_time}")


@app.route('/')
def display_docker_data():
    """Display Docker image data with last checked and scheduled next run times."""
    global docker_image_data, dots, next_run_time, last_checked_time
    return render_template(
        'index.html',
        data=docker_image_data,
        orange_dot=dots["orange"],
        green_dot=dots["green"],
        red_dot=dots["red"],
        yellow_dot=dots["yellow"],
        next_run=next_run_time,
        last_checked=last_checked_time
    )


@app.route('/health', methods=['GET'])
def health_check():
    try:
        logger.debug("Health check endpoint called")
        return jsonify({"status": "healthy"}), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


def run_flask():
    """Run Flask app in a separate thread."""
    app.run(host='0.0.0.0', port=5151, debug=False, use_reloader=False)


if __name__ == "__main__":
    """Initialize and start monitoring."""
    platform_base_url = getPlatformBaseUrl()
    docker_info = getDockerInfo()
    node_name = docker_info["docker_engine_name"]
    old_list = []
    config_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.json")
    file_db = os.path.join(os.path.dirname(os.path.realpath(__file__)), "data.db")
    
    if os.path.exists(file_db):
        with open(file_db, "r") as file:
            old_list = file.readlines()
    
    dots = {"orange": "\U0001F7E0", "green": "\U0001F7E2", "red": "\U0001F534", "yellow": "\U0001F7E1"}
    square_dots = {"orange": "\U0001F7E7", "green": "\U0001F7E9", "red": "\U0001F7E5", "yellow": "\U0001F7E8"}
    header_message = f"*{node_name}* (.digest)\n"
    monitoring_message = f"- docker engine: {docker_info['docker_version']},\n"
    
    if os.path.exists(config_file):
        with open(config_file, "r") as file:
            config_json = json.loads(file.read())
        try:
            startup_message = config_json.get("STARTUP_MESSAGE", True)
            default_dot_style = config_json.get("DEFAULT_DOT_STYLE", True)
            min_repeat = max(int(config_json.get("MIN_REPEAT", 15)), 15)
        except (json.JSONDecodeError, ValueError, TypeError, KeyError):
            startup_message, default_dot_style = True, True
            min_repeat = 15
            logger.error("Error or incorrect settings in config.json. Using defaults.")
        if not default_dot_style:
            dots = square_dots
        orange_dot = dots["orange"]
        no_messaging_keys = ["STARTUP_MESSAGE", "DEFAULT_DOT_STYLE", "MIN_REPEAT"]
        messaging_platforms = list(set(config_json) - set(no_messaging_keys))
        for platform in messaging_platforms:
            if config_json[platform].get("ENABLED", False):
                for key, value in config_json[platform].items():
                    platform_key = f"platform_{key.lower()}"
                    if platform_key in globals():
                        globals()[platform_key] = (globals()[platform_key] if isinstance(globals()[platform_key], list) else [globals()[platform_key]])
                        globals()[platform_key].extend(value if isinstance(value, list) else [value])
                    else:
                        globals()[platform_key] = value if isinstance(value, list) else [value]
                monitoring_message += f"- messaging: {platform.lower().capitalize()},\n"
        monitoring_message = "\n".join([*sorted(monitoring_message.splitlines()), ""])
        st_message = "Yes" if startup_message else "No"
        dt_style = "Round" if default_dot_style else "Square"
        monitoring_message += (
            f"- startup message: {st_message},\n"
            f"- dot style: {dt_style},\n"
            f"- polling period: {min_repeat} minutes."
        )
        if all(value in globals() for value in ["platform_webhook_url", "platform_header", "platform_payload", "platform_format_message"]):
            logger.info("Initialization complete!")
            if startup_message:
                SendMessage(f"{header_message}{monitoring_message}")
        else:
            logger.error("Invalid config.json")
            sys.exit(1)
    else:
        logger.error("config.json not found")
        sys.exit(1)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask web server started at http://0.0.0.0:5151")

    watchDigest()

    @repeat(every(min_repeat).minutes)
    def RepeatCheck():
        watchDigest()

    while True:
        run_pending()
        time.sleep(1)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2025 2boom.

import json
import docker
import os
import time
import sys
import socket
import requests
import logging
import platform
import subprocess
import schedule
import random
import threading
from typing import List, Dict
from schedule import every, repeat, run_pending
from collections import deque
from docker.errors import DockerException
from urllib.parse import urlparse
from datetime import datetime, time as dtime, timedelta
from flask import Flask, render_template, jsonify, request, Response

default_start_times = ["03:00", "15:00"]
upgrade_mode = True
default_compose_files = ['compose.yaml', 'compose.yml', 'docker-compose.yaml', 'docker-compose.yml']
list_of_outdated_images = []
start_times_outdate_check = []
docker_image_data = []
old_list = []

class LimitedMemoryHandler(logging.Handler):
    def __init__(self, capacity=1000):
        super().__init__()
        self.log_buffer = deque(maxlen=capacity)

    def emit(self, record):
        formatted_message = self.format(record)
        self.log_buffer.append(formatted_message)

    def get_logs(self):
        return list(self.log_buffer)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if logger.hasHandlers():
    logger.handlers.clear()

limited_handler = LimitedMemoryHandler(capacity=1000)
limited_handler.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
limited_handler.setFormatter(formatter)

logger.addHandler(limited_handler)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.disabled = True

app = Flask(__name__)
app.logger.disabled = True

def cut_message_url(url):
    """Truncate URL for logging brevity."""
    parsed_url = urlparse(url)
    return f"{parsed_url.scheme}://{parsed_url.netloc}...."


def get_platform_base_url() -> str:
    """Return Docker socket path based on OS."""
    return 'unix://var/run/docker.sock' if platform.system() == "Linux" else 'npipe:////./pipe/docker_engine'


def get_docker_engine_info() -> dict:
    """Fetch Docker node name and version."""
    try:
        docker_client = docker.DockerClient(base_url=platform_base_url)
        return {
            "docker_engine_name": docker_client.info().get("Name", ""),
            "docker_version": docker_client.version().get("Version", "")
        }
    except (DockerException, Exception) as e:
        logger.error(f"Error fetching Docker info: {e}.")
        return {"docker_engine_name": "", "docker_version": ""}


def get_compose_version() -> dict:
    """Return Docker Compose version as a dict: {'docker_compose_version': '<version>'}, or 'N/A' if not found."""

    def extract_version(output):
        for line in output.splitlines():
            if 'version' in line.lower():
                if 'v' in line and '.' in line:
                    version = line.split('v')[-1].split()[0]
                    if version.replace('.', '').isdigit():
                        return version
                for part in line.split():
                    if part[0].isdigit() and '.' in part:
                        version = part.split(',')[0]
                        if version.replace('.', '').isdigit():
                            return version
        return None

    commands = [
        ["docker", "compose", "version"],
        ["docker-compose", "version"]
    ]

    for cmd in commands:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            version = extract_version(result.stdout)
            if version:
                return {"docker_compose_version": version}
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue

    return {"docker_compose_version": "N/A"}


def send_message(message: str):
    """Send HTTP POST requests with retry logic."""
    def send_request(url, json_data=None, data=None, headers=None):
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                response = requests.post(url, json=json_data, data=data, headers=headers, timeout=(5, 20))
                response.raise_for_status()
                return
            except requests.exceptions.RequestException as e:
                logger.error(f"Attempt {attempt + 1}/{max_attempts} - Error sending to {cut_message_url(url)}: {e}.")
                if attempt == max_attempts - 1:
                    logger.error(f"Failed to send to {cut_message_url(url)} after {max_attempts} attempts.")
                else:
                    backoff_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Retrying in {backoff_time:.2f} seconds...")
                    time.sleep(backoff_time)

    def to_html_format(message: str) -> str:
        """Convert message to HTML bold format."""
        message = ''.join(f"<b>{part}</b>" if i % 2 else part for i, part in enumerate(message.split('*')))
        return message.replace("\n", "<br>")

    def to_markdown_format(message: str, markdown_type: str) -> str:
        """Format message based on specified type."""
        if markdown_type == "html":
            return to_html_format(message)
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
        formatted_message = to_markdown_format(message, format_message)
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
        send_request(url, payload_json, data, header_json)


def deduplicate_data(data):
    """Remove duplicates from data, preferring non-library images."""
    seen = {}

    for entry in data:
        key = tuple(
            (k, tuple(v) if isinstance(v, list) else v)
            for k, v in sorted(entry.items()) if k != 'image'
        )

        if key in seen:
            current_image = entry['image']
            stored_image = seen[key]['image']
            if not current_image.startswith('docker.io/library/') and stored_image.startswith('docker.io/library/'):
                seen[key] = entry.copy()
        else:
            seen[key] = entry.copy()

    return list(seen.values())


def get_non_dangling_images() -> List[Dict[str, str]]:
    global docker_image_data

    resource_data = []
    try:
        docker_client = docker.DockerClient(base_url=platform_base_url, version="auto")
        images = docker_client.images.list(filters={'dangling': False})
        containers = docker_client.containers.list(all=True)

        used_image_ids = {container.image.id for container in containers}
        
        for image in images:

            if image.id not in used_image_ids:
                continue

            image_tags = image.tags if image.tags else [image.attrs.get("RepoDigests", ["<untagged>"])[0]]
            
            repo_digests = image.attrs.get("RepoDigests", [])
            
            is_local = not repo_digests
            
            if is_local:
                digest = f"sha256:{image.id.split(':')[-1]}"
            else:
                raw_digest = repo_digests[0] if repo_digests else None
                digest = raw_digest.split('@')[1] if raw_digest and '@' in raw_digest else "unknown"

            size_mb = image.attrs.get("Size", 0) / (1024 * 1024)

            created_raw = image.attrs.get("Created", None)
            created = "Unknown"
            if created_raw:
                try:
                    if '.' in created_raw:
                        base, frac = created_raw.split('.')
                        frac = frac.rstrip('Z')
                        frac = (frac + "000000")[:6]
                        created_raw_truncated = f"{base}.{frac}Z"
                        created_dt = datetime.strptime(created_raw_truncated, "%Y-%m-%dT%H:%M:%S.%fZ")
                    else:
                        created_dt = datetime.strptime(created_raw, "%Y-%m-%dT%H:%M:%SZ")
                    created = created_dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    logger.error(f"Error parsing Created timestamp: {e}.")

            for tag in image_tags:
                parts = tag.split('/')
                if is_local:
                    image_name_tag = parts[-1]
                    image_tag = f'local/{image_name_tag}'
                else:
                    if len(parts) == 1:
                        image_tag = f'docker.io/library/{tag}'
                    elif '.' not in parts[0] and ':' not in parts[0]:
                        image_tag = f'docker.io/{tag}'
                    else:
                        image_tag = tag

                container_names = [
                    container.name for container in containers if container.image.id == image.id
                ]
                if "@sha256" in image_tag:
                    image_tag = f"local/{image_tag.split('@')[0]}:<none>"
                resource_data.append({
                    "container_name": container_names,
                    "digest": digest,
                    "image": image_tag,
                    "size": f"{size_mb:.2f} MB",
                    "status": "uptodate",
                    "created": created
                })

    except (DockerException, Exception) as e:
        logger.error(f"Error retrieving Docker data: {e}.")

    resource_data = deduplicate_data(resource_data)

    resource_data.sort(key=lambda x: x["container_name"][0] if x["container_name"] else "")
    for idx, item in enumerate(resource_data, start=1):
        item["count"] = idx
    docker_image_data = resource_data

    return resource_data


def get_registry_digest(registry: str, owner: str, image: str, tag: str) -> str:
    """Retrieve the latest digest for a Docker image from a registry."""
    digest = ""
    max_retries, retry_delay = 3, 2

    if registry in ["lscr.io", "ghcr.io"]:
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
            elif response.status_code == 401:
                logger.error(f"Authentication failed for {manifest_url}.")
                return digest
            else:
                time.sleep(retry_delay)

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {e}.")

    return digest


def get_outdated_digests() -> List[dict]:
    """Check for outdated Docker images and return list with container names and image info."""
    outdated_images = []
    seen = set()

    for data in get_non_dangling_images():
        local_digest = data["digest"]
        full_image = data["image"]
        container_names = data["container_name"]

        if full_image.startswith("local/") or local_digest == "unknown":
            continue

        try:
            source, rest = full_image.split("/", 1)
            owner_image, tag = rest.rsplit(":", 1)
            owner, image = owner_image.split("/", 1) if "/" in owner_image else ("library", owner_image)
        except ValueError:
            logger.warning(f"Unable to parse image: {full_image}.")
            continue

        if source.startswith(("docker.io", "ghcr.io", "lscr.io", "registry.")):
            remote_digest = get_registry_digest(source, owner, image, tag)
            display_image = full_image.replace("docker.io/", "") if source.startswith("docker.io") else full_image

            if remote_digest and remote_digest != local_digest:
                unique_containers = set(container_names)
                for container in unique_containers:
                    entry = {"container_name": container, "image": display_image}
                    entry_tuple = (container, display_image)
                    if entry_tuple not in seen:
                        seen.add(entry_tuple)
                        outdated_images.append(entry)

    if outdated_images:
        for image in outdated_images:
            logger.info(f"Outdated image detected - Container: {image['container_name']}, Image: {image['image']}.")

    return outdated_images


def get_outdated_digests_list():
    """Check for outdated Docker images and return list with container names and image info."""
    global old_list, docker_image_data

    docker_image_data = get_non_dangling_images()
    new_list = result = []
    count_all = count_with_digest = 0

    for data in docker_image_data:
        local_digest = data["digest"]
        full_image = data["image"]
        container_names = data["container_name"]

        try:
            source, rest = full_image.split("/", 1)
            owner_image, tag = rest.rsplit(":", 1)
            owner, image = owner_image.split("/", 1) if "/" in owner_image else ("library", owner_image)
        except ValueError:
            logger.warning(f"Unable to parse image: {full_image}.")
            data["status"] = "error"
            continue

        if source.startswith(("docker.io", "ghcr.io", "lscr.io", "registry.")):
            digest = get_registry_digest(source, owner, image, tag)
            if digest:
                count_with_digest += 1

            if digest:
                if digest != local_digest:
                    data["status"] = "outdated"
                    new_list.append(f"{orange_dot} *{owner}/{image}:{tag}* outdated!\n")
                else:
                    data["status"] = "uptodate"
            else:
                data["status"] = "error"

        elif source.startswith("local"):
            data["status"] = "unable"
        else:
            data["status"] = "error"

        count_all += 1

    if new_list and len(new_list) >= len(old_list):
        result = [item for item in new_list if item not in old_list]

    old_list = new_list

    with open(file_db, "w") as file:
        file.writelines(new_list)

    logger.info(f"{count_all} local digests tracked, {count_with_digest} completed.")

    if result:
        if notify_enabled:
            send_message(f"{header_message}{''.join(result)}")
        for item in result:
            logger.info(f"{str(item).replace(orange_dot, white_dot).replace('*', '').strip()}")


def pull_and_restart_outdated_images():
    """Pull updated images, restart containers, and remove unused images."""
    def find_compose_file(working_dir):
        try:
            if not os.path.isdir(working_dir):
                logger.error(f"Directory {working_dir} does not exist.")
                return None

            dir_contents = os.listdir(working_dir)
            for compose_file in compose_files:
                if compose_file in dir_contents:
                    return os.path.join(working_dir, compose_file)

            logger.info(f"No valid compose file found in {working_dir}.")
            return None

        except FileNotFoundError:
            logger.error(f"Directory {working_dir} does not exist.")
            return None
        except PermissionError:
            logger.error(f"Permission denied accessing {working_dir}.")
            return None

    def get_compose_command():
        """Determine whether to use 'docker compose' (v2) or 'docker-compose' (v1)"""
        try:
            subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                check=True
            )
            return ["docker", "compose"]
        except FileNotFoundError:
            logger.error("'docker' command not found in PATH.")
        except subprocess.CalledProcessError as e:
            logger.error(f"'docker compose' exists but failed: {e.stderr.decode().strip()}")

        try:
            subprocess.run(
                ["docker-compose", "version"],
                capture_output=True,
                check=True
            )
            return ["docker-compose"]
        except FileNotFoundError:
            logger.error("'docker-compose' command not found in PATH.")
        except subprocess.CalledProcessError as e:
            logger.error(f"'docker-compose' exists but failed: {e.stderr.decode().strip()}")

        logger.error("Neither 'docker compose' (v2) nor 'docker-compose' (v1) is installed or functional.")
        raise RuntimeError("Neither 'docker compose' (v2) nor 'docker-compose' (v1) is installed.")

    try:
        docker_client = docker.DockerClient(base_url=platform_base_url, version="auto")
        outdated = list_of_outdated_images

        used_images_before = {c.image.id for c in docker_client.containers.list(all=True)}

        successful_pulls = set()
        for entry in outdated:
            image = entry["image"]
            logger.info(f"Pulling updated image for: {image}.")
            try:
                docker_client.images.pull(image)
                logger.info(f"Successfully pulled: {image}.")
                successful_pulls.add(image)
            except docker.errors.APIError as e:
                logger.error(f"Failed to pull {image}: {e}.")
            time.sleep(10)

        for entry in outdated:
            image = entry["image"]
            container_name = entry["container_name"]
            
            if image not in successful_pulls:
                logger.info(f"Skipping container {container_name} - image {image} was not successfully pulled!")
                continue

            container = docker_client.containers.get(container_name)
            working_dir = container.attrs['Config']['Labels'].get('com.docker.compose.project.working_dir')

            if working_dir:
                compose_file_name = find_compose_file(working_dir)
                compose_cmd = get_compose_command()
                logger.info(f"Restarting container {container_name} using docker compose in {working_dir}{compose_file_name}.")
                try:
                    subprocess.run(
                        compose_cmd + ["-f", compose_file_name, "up", "-d", container_name],
                        cwd=working_dir,
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to restart using docker compose in {working_dir}: {e}.")
            else:
                logger.info(f"Restarting container {container_name} using Docker SDK.")
                try:
                    container.stop()
                    container.remove()
                    docker_client.containers.run(image, name=container_name, detach=True)
                except docker.errors.APIError as e:
                    logger.error(f"Failed to restart {container_name}: {e}.")

        used_images_after = {c.image.id for c in docker_client.containers.list(all=True)}
        unused_images = used_images_before - used_images_after

        for image_id in unused_images:
            try:
                docker_client.images.remove(image_id)
                logger.info(f"Removed unused image: {image_id}.")
            except docker.errors.APIError as e:
                logger.warning(f"Failed to remove image {image_id}: {e}.")
        time.sleep(10)

    except DockerException as e:
        logger.error(f"Error in updating and restarting containers: {e}.")


def maintain_container_images():
    logger.info("Checking for outdated container images that need upgrading...")
    global list_of_outdated_images
    next_run_time = get_next_start_time(start_times)
    time_start = datetime.now()

    list_of_outdated_images = get_outdated_digests()
    if list_of_outdated_images:
        # logger.info("Simulating image pull and container restart...")
        pull_and_restart_outdated_images()

    get_outdated_digests_list()
    time_end = datetime.now()
    elapsed = time_end - time_start
    minutes, seconds = divmod(elapsed.total_seconds(), 60)
    logger.info(f"Image upgrade check completed in {int(minutes):02d}:{int(seconds):02d}.")
    logger.info(f"Next scheduled image upgrade check: {next_run_time}.")


def checkonly_container_images():
    logger.info("Checking for outdated container images (no actions will be taken)...")
    start_times_outdate_check = get_starts_check_times(start_times, upgrade_mode)
    next_run_time = get_next_start_time(start_times_outdate_check)
    time_start = datetime.now()

    get_outdated_digests_list()

    time_end = datetime.now()
    elapsed = time_end - time_start
    minutes, seconds = divmod(elapsed.total_seconds(), 60)
    logger.info(f"Outdated image check completed in {int(minutes):02d}:{int(seconds):02d}.")
    logger.info(f"Next scheduled outdated image check: {next_run_time}.")


def get_next_start_time(start_times):
    now = datetime.now()
    current_time = now.time()

    if not start_times:
        start_times = default_start_times

    time_objects = [datetime.strptime(t, "%H:%M").time() for t in start_times if t]

    if not time_objects:
        time_objects = [datetime.strptime(t, "%H:%M").time() for t in default_start_times]

    for t in time_objects:
        if current_time < t:
            return datetime.combine(now.date(), t).strftime("%Y-%m-%d %H:%M")

    tomorrow = now.date() + timedelta(days=1)
    return datetime.combine(tomorrow, time_objects[0]).strftime("%Y-%m-%d %H:%M")


def get_starts_check_times(start_times, upgrade_mode=True):
    timeshift_minutes = 40
    check_times = set()
    parsed_times = [datetime.strptime(t, "%H:%M") for t in start_times]
    parsed_times.sort()

    for i in range(1, len(parsed_times)):
        time_diff = (parsed_times[i] - parsed_times[i-1]).total_seconds() / 60
        if time_diff < timeshift_minutes:
            raise ValueError(f"Start times {parsed_times[i-1].strftime('%H:%M')} and "
                           f"{parsed_times[i].strftime('%H:%M')} are less than "
                           f"{timeshift_minutes} minutes apart")

    all_times = []
    for i, start in enumerate(parsed_times):
        new_time_decrease = start - timedelta(minutes=timeshift_minutes)
        new_time_increase = start + timedelta(minutes=timeshift_minutes)
        additional_time = start - timedelta(minutes=timeshift_minutes * 2)

        check_times.add(new_time_decrease.strftime("%H:%M"))
        check_times.add(new_time_increase.strftime("%H:%M"))
        all_times.extend([new_time_decrease, new_time_increase])

        add_additional = True
        for prev_time in all_times:
            time_diff = abs((additional_time - prev_time).total_seconds() / 60)
            if time_diff < timeshift_minutes:
                add_additional = False
                break

        if add_additional:
            check_times.add(additional_time.strftime("%H:%M"))
            all_times.append(additional_time)

        if not upgrade_mode:
            all_times.append(start)

    if not upgrade_mode:
        for start in parsed_times:
            check_times.add(start.strftime("%H:%M"))
            if start not in all_times:
                all_times.append(start)

    all_times.sort()
    for i in range(1, len(all_times)):
        time_diff = (all_times[i] - all_times[i-1]).total_seconds() / 60
        if time_diff < timeshift_minutes:
            raise ValueError(f"Generated times {all_times[i-1].strftime('%H:%M')} and "
                           f"{all_times[i].strftime('%H:%M')} are less than "
                           f"{timeshift_minutes} minutes apart")

    return sorted(list(check_times))


@app.route("/logs")
def stream_logs():
    """Stream the last log records."""
    def generate():
        for line in limited_handler.get_logs():
            yield f"{line}<br>"
    return Response(generate(), mimetype="text/html")


@app.route('/')
def display_docker_data():
    """Display Docker image data with last checked and scheduled next run times."""
    display_data = []

    for data in docker_image_data:
        temp = data.copy()
        if isinstance(temp["container_name"], list):
            temp["container_name"] = ", ".join(temp["container_name"])
        temp["image"] = temp["image"].replace("docker.io/", "").replace("local/", "")
        display_data.append(temp)

    return render_template(
        'index.html',
        data=display_data,
        orange_emoji=orange_dot,
        green_emoji=green_dot,
        red_emoji=red_dot,
        yellow_emoji=yellow_dot,
        white_emoji=white_dot,
    )


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    try:
        return jsonify({"status": "healthy"}), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}.")
        return jsonify({"status": "error", "message": str(e)}), 500


def run_flask():
    """Run Flask app in a separate thread."""
    app.run(host='0.0.0.0', port=5151, debug=False, use_reloader=False)


if __name__ == "__main__":
    """Initialize and start monitoring."""
    logger.info("Starting container image monitor...")

    config_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.json")
    file_db = os.path.join(os.path.dirname(os.path.realpath(__file__)), "data.db")

    platform_base_url = get_platform_base_url()
    start_times = default_start_times

    compose_files = default_compose_files

    dots = {"orange": "\U0001F7E0", "green": "\U0001F7E2", "red": "\U0001F534", "yellow": "\U0001F7E1", "white": "\U000026AA"}
    square_dots = {"orange": "\U0001F7E7", "green": "\U0001F7E9", "red": "\U0001F7E5", "yellow": "\U0001F7E8", "white": "\U0001F533"}

    docker_info = get_docker_engine_info()
    node_name = docker_info.get("docker_engine_name", "Unknown")
    monitoring_message = ""
    compose_version = get_compose_version()

    logger.info(f"docker engine: {docker_info.get('docker_version', 'N/A')}.")
    logger.info(f"docker compose: {compose_version.get('docker_compose_version', 'N/A')}.")

    header_message = (
        f"*{node_name}* (.digest)\n"
        f"- docker engine: {docker_info.get('docker_version', 'N/A')},\n"
        f"- docker compose: {compose_version.get('docker_compose_version', 'N/A')},\n"
        f"- auto-upgrade mode: {'On' if upgrade_mode else 'Off'},\n"
    )

    if os.path.exists(file_db):
        try:
            with open(file_db, "r") as file:
                old_list = file.readlines()
        except Exception as e:
            logger.warning(f"Unable to read {file_db}: {e}.")

    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as file:
                config_json = json.load(file)
            startup_message = config_json.get("STARTUP_MESSAGE", True)
            notify_enabled = config_json.get("NOTIFY_ENABLED", False)
            default_dot_style = config_json.get("DEFAULT_DOT_STYLE", True)
            upgrade_mode = config_json.get("UPGRADE_MODE", True)
            start_times = config_json.get("START_TIMES", default_start_times)
            compose_files = config_json.get("COMPOSE_FILES", default_compose_files)
        except (json.JSONDecodeError, ValueError, TypeError, KeyError) as e:
            logger.error(f"Error reading or parsing config.json: {e}. Using default times.")
    else:
        logger.error("config.json not found. Using default times.")

    if not notify_enabled:
        startup_message = False

    if not default_dot_style:
        dots = square_dots
    orange_dot, green_dot, red_dot, yellow_dot, white_dot = dots.values()

    no_messaging_keys = ["STARTUP_MESSAGE", "NOTIFY_ENABLED", "DEFAULT_DOT_STYLE", "UPGRADE_MODE", "START_TIMES", "COMPOSE_FILES"]
    if notify_enabled:
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
        monitoring_message += (
            f"- startup message: {'On' if startup_message else 'Off'},\n"
            f"- dot style: {'Round' if default_dot_style else 'Square'}.\n"
        )

        if all(value in globals() for value in ["platform_webhook_url", "platform_header", "platform_payload", "platform_format_message"]):
            if startup_message:
                send_message(f"{header_message}{monitoring_message}")

    header_message = header_message.split('\n')[0]
    header_message = f"{header_message}\n"

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info(f"Initialization complete. Auto-upgrade mode: {'On' if upgrade_mode else 'Off'}.")
    logger.info(f"Notifications to a messaging system: {'On' if notify_enabled else 'Off'}.")

    try:
        start_times_outdate_check = get_starts_check_times(start_times, upgrade_mode)
        if upgrade_mode:
            logger.info(f"Using check times for image upgrade: {', '.join(start_times)}.")
        logger.info(f"First scheduled image upgrade check: {get_next_start_time(start_times)}.")
    except ValueError as e:
        start_times_outdate_check = get_starts_check_times(default_start_times, upgrade_mode)
        logger.error(f"Error: {e}")
        logger.warning(f"Invalid start time settings in config.json. Using default values: {start_times}. Please update the configuration.")

    checkonly_container_images()

    for stime in start_times_outdate_check:
        schedule.every().day.at(stime).do(checkonly_container_images)

    if upgrade_mode:
        for stime in start_times:
            schedule.every().day.at(stime).do(maintain_container_images)

    while True:
        schedule.run_pending()
        time.sleep(60)
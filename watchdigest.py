#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#Copyright (c) 2025 2boom.

import json
import docker
import os
import time
import requests
import socket
import logging
import platform
from schedule import every, repeat, run_pending
from docker.errors import DockerException
from urllib.parse import urlparse
from datetime import datetime, timedelta


"""Configure logging"""
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("whatchdigest")


def cutMessageUrl(url):
    """Cut message url"""
    parsed_url = urlparse(url)
    return f"{parsed_url.scheme}://{parsed_url.netloc}...."


def getPlatformBaseUrl() -> str:
    """Returns the Docker socket path based on the OS."""
    return 'unix://var/run/docker.sock' if platform.system() == "Linux" else 'npipe:////./pipe/docker_engine'


def getDockerInfo() -> dict:
    """Get Docker node name and version."""
    try:
        docker_client = docker.DockerClient(base_url=platform_base_url)
        return {
            "node_name": docker_client.info().get("Name", ""),
            "docker_version": docker_client.version().get("Version", "")
        }
    except (docker.errors.DockerException, Exception) as e:
        logger.error(f"Error: {e}")
        return {"node_name": "", "docker_version": ""}


def SendMessage(message: str):
    """Internal function to send HTTP POST requests with error handling"""
    def SendRequest(url, json_data=None, data=None, headers=None):
        try:
            response = requests.post(url, json=json_data, data=data, headers=headers)
            response.raise_for_status()
            logger.info(f"Message successfully sent to {cutMessageUrl(url)}. Status code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending message to {cutMessageUrl(url)}: {e}")

    """"Converts Markdown-like syntax to HTML format."""
    def toHTMLFormat(message: str) -> str:
        message = ''.join(f"<b>{part}</b>" if i % 2 else part for i, part in enumerate(message.split('*')))
        return message.replace("\n", "<br>")

    """Converts the message to the specified format (HTML, Markdown, or plain text)"""
    def toMarkdownFormat(message: str, m_format: str) -> str:
        if m_format == "html":
            return toHTMLFormat(message)
        elif m_format == "markdown":
            return message.replace("*", "**")
        elif m_format == "text":
            return message.replace("*", "")
        elif m_format == "simplified":
            return message
        else:
            logger.error(f"Unknown format '{m_format}' provided. Returning original message.")
            return message

    """Iterate through multiple platform configurations"""
    for url, header, pyload, format_message in zip(platform_webhook_url, platform_header, platform_pyload, platform_format_message):
        data, ntfy = None, False
        formated_message = toMarkdownFormat(message, format_message)
        header_json = header if header else None
        
        for key in list(pyload.keys()):
            if key == "title":
                delimiter = "<br>" if format_message == "html" else "\n"
                header, formated_message = formated_message.split(delimiter, 1)
                pyload[key] = header.replace("*", "")
            elif key == "extras":
                formated_message = formated_message.replace("\n", "\n\n")
                pyload["message"] = formated_message
            elif key == "data":
                ntfy = True
            pyload[key] = formated_message if key in ["text", "content", "message", "body", "formatted_body", "data"] else pyload[key]
        pyload_json = None if ntfy else pyload
        data = formated_message.encode("utf-8") if ntfy else None
        """Send the request with the appropriate payload and headers"""
        SendRequest(url, pyload_json, data, header_json)


def getDockerData() -> list:
    """Retrieve detailed data for Docker images"""
    resource_data = []
    try:
        docker_client = docker.DockerClient(base_url='unix://var/run/docker.sock', version='auto')
        images = docker_client.images.list()
        if images:
            for image in images:
                if not image.tags or ":" not in image.tags[0]:
                    continue
                image_full, image_tag = image.tags[0].split(':', 1)
                parts = image_full.split('/')
                if len(parts) == 3:
                    image_source, image_owner, image_name = parts
                elif len(parts) == 2:
                    image_source = "docker.io"
                    image_owner, image_name = parts
                elif len(parts) == 1:
                    image_source, image_owner, image_name = "local", "dockerfile", image_full
                else:
                    image_source, image_owner, image_name = "docker.io", "library", parts[0]
                digest = image.attrs["RepoDigests"][0].split("@")[1] if image.attrs.get("RepoDigests") else "NoDigest"
                resource_data.append(f"{digest} {image_source} {image_owner} {image_name} {image_tag}")
    except (docker.errors.DockerException, Exception) as e:
        logger.error(f"Error: {e}")
    return resource_data


def getDockerDigest(registry: str, owner: str, image: str, tag: str, ghcr_pat: str = None) -> str:
    """Retrieves the latest digest for a Docker image from GHCR, Docker Hub, GitLab, or a custom registry."""
    digest = token = ""
    max_retries, retry_delay = 3, 2
    if registry == "ghcr.io":
        auth_url = f"https://ghcr.io/token?scope=repository:{owner}/{image}:pull"
        manifest_url = (
            f"https://api.github.com/users/{owner}/packages/container/{image}/versions"
            if ghcr_pat else f"https://ghcr.io/v2/{owner}/{image}/manifests/{tag}"
        )
    elif registry == "docker.io":
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
        if registry == "ghcr.io" and ghcr_pat:
            token = ghcr_pat
        else:
            response_token = requests.get(auth_url, params=auth_params if registry == "docker.io" else None)
            if response_token.status_code == 200:
                token = response_token.json().get("token", "")
            else:
                return digest
        headers = {
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Accept": ", ".join([
                "application/vnd.docker.distribution.manifest.v2+json",
                "application/vnd.docker.distribution.manifest.list.v2+json",
                "application/vnd.oci.image.manifest.v1+json",
                "application/vnd.github+json"
            ])
        }
        for attempt in range(max_retries):
            response = requests.get(manifest_url, headers=headers) if ghcr_pat and registry == "ghcr.io" else requests.head(manifest_url, headers=headers)
            if response.status_code == 200:
                if ghcr_pat and registry == "ghcr.io":
                    versions = response.json()
                    for version in versions:
                        if tag in version.get('metadata', {}).get('container', {}).get('tags', []):
                            return version['name']
                else:
                    return response.headers.get("Docker-Content-Digest", "")
            if response.status_code == 404:
                return digest
            time.sleep(retry_delay)
    except requests.exceptions.RequestException as e:
        logger.error(f"Error: {e}")
    return digest


def watchDigest():
    """Checks for outdated Docker images by comparing local digests with remote ones."""
    global old_list
    new_list = result = []
    current_time = datetime.now()
    count_all = count_with_digest = 0
    for dockerdata in getDockerData():
        local_digest, source, owner, image, tag = dockerdata.split()
        if source.startswith(("docker.io", "ghcr.io", "registry.gitlab.com", "registry.")):
            digest = getDockerDigest(source, owner, image, tag, ghcr_pat)
        else:
            continue
        if digest:
            count_with_digest += 1
        if digest and digest != local_digest:
            new_list.append(f"{orange_dot} *{owner}/{image}*: outdated!\n")
        count_all += 1
    if new_list:
        if len(new_list) >= len(old_list):
            result = [item for item in new_list if item not in old_list]
    old_list = new_list
    with open(file_db, "w") as file:
        file.writelines(old_list)
    if result:
        SendMessage(f"{header_message}{''.join(result)}")
        logger.info(f"{''.join(result).replace(orange_dot, '').replace('*', '').strip()}")
    logger.info("Process complete!")
    logger.info(f"{count_all} local digests tracked, {count_with_digest} completed.")
    new_time = current_time + timedelta(minutes=min_repeat)
    logger.info(f"Scheduled next run: {new_time.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    """Load configuration and initialize monitoring"""
    platform_base_url = getPlatformBaseUrl()
    docker_info = getDockerInfo()
    node_name = docker_info["node_name"]
    old_list = []
    config_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.json")
    file_db = os.path.join(os.path.dirname(os.path.realpath(__file__)), "data.db")
    if os.path.exists(file_db):
        with open(file_db, "r") as file:
            old_list.extend(file.readlines())
    dots = {"orange": "\U0001F7E0"}
    square_dots = {"orange": "\U0001F7E7"}
    header_message = f"*{node_name}* (.digest)\n"
    monitoring_message = f"- docker engine: {docker_info['docker_version']},\n"
    if os.path.exists(config_file):
        with open(config_file, "r") as file:
            config_json = json.loads(file.read())
        try:
            startup_message = config_json.get("STARTUP_MESSAGE", True)
            default_dot_style = config_json.get("DEFAULT_DOT_STYLE", True)
            ghcr_pat = config_json.get("GHCR_PAT", "")
            min_repeat = max(int(config_json.get("MIN_REPEAT", 15)), 15)
        except (json.JSONDecodeError, ValueError, TypeError, KeyError):
            startup_message, default_dot_style = True, True
            min_repeat, ghcr_pat = 15, ""
            logger.error("Error or incorrect settings in config.json. Default settings will be used.")
        if not default_dot_style:
            dots = square_dots
        orange_dot = dots["orange"]
        no_messaging_keys = ["GHCR_PAT", "STARTUP_MESSAGE", "DEFAULT_DOT_STYLE", "MIN_REPEAT"]
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
        pt_ghcr = "Yes" if ghcr_pat else "No"
        monitoring_message += (
            f"- startup message: {st_message},\n"
            f"- dot style: {dt_style},\n"
            f"- use GHCR PAT: {pt_ghcr},\n"
            f"- polling period: {min_repeat} minutes."
        )
        if all(value in globals() for value in ["platform_webhook_url", "platform_header", "platform_pyload", "platform_format_message"]):
            logger.info(f"Initialization complete!")
            if startup_message:
                SendMessage(f"{header_message}{monitoring_message}")
            watchDigest()
        else:
            logger.error("config.json is wrong")
            sys.exit(1)
    else:
        logger.error("config.json not found")
        sys.exit(1)

    
"""Periodically check for changes in Docker monitoring images"""
@repeat(every(min_repeat).minutes)
def RepeatCheck():
    watchDigest()

while True:
    run_pending()
    time.sleep(1)

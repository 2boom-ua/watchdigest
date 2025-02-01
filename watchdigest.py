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
from schedule import every, repeat, run_pending
from docker.errors import DockerException
from urllib.parse import urlparse
from datetime import datetime, timedelta


"""Configure logging"""
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("whatchdigesty")


def getBaseUrl(url):
    """Get base url"""
    parsed_url = urlparse(url)
    return f"{parsed_url.scheme}://{parsed_url.netloc}...."


def getDockerInfo() -> dict:
    """Get Docker node name and version."""
    try:
        docker_client = docker.DockerClient(base_url='unix://var/run/docker.sock')
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
            logger.info(f"Message successfully sent to {getBaseUrl(url)}. Status code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending message to {getBaseUrl(url)}: {e}")

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


def getDockerData() -> tuple:
    """Retrieve detailed data for Docker images"""
    resource_data = []
    try:
        docker_client = docker.DockerClient(base_url='unix://var/run/docker.sock', version='auto')
        images = docker_client.images.list()
        if images:
            for image in images:
                if not image.tags:
                    continue
                if not ":" in image.tags[0]:
                    continue
                image_full, image_tag = image.tags[0].split(':')
                parts = image_full.split('/')
                if len(parts) == 3:
                    image_source, image_owner, image_name = parts                       
                elif len(parts) == 1:
                    image_source = "local"
                    image_owner = "dockerfile"
                    image_name = image_full
                else:
                    image_source = "docker.io"
                    image_owner, image_name = parts

                if image.attrs["RepoDigests"]:
                    digest = image.attrs["RepoDigests"][0].split("@")[1]
                else:
                    digest = "NoDigest"
                resource_data.append(f"{digest} {image_source} {image_owner} {image_name} {image_tag}")
    except (docker.errors.DockerException, Exception) as e:
        logger.error(f"Error: {e}")
    return resource_data


def get_ghcr_digest(owner, image, tag):
    # Get token for public repository
    auth_url = f"https://ghcr.io/token?scope=repository:{owner}/{image}:pull"
    response = requests.get(auth_url)
    
    if response.status_code != 200:
        raise Exception(f"Failed to get token: {response.text}")
    
    token = response.json().get("token")
    
    # Fetch manifest to get digest
    manifest_url = f"https://ghcr.io/v2/{owner}/{image}/manifests/{tag}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.docker.distribution.manifest.v2+json"
    }
    
    response = requests.head(manifest_url, headers=headers)
    
    if response.status_code == 200:
        return response.headers.get("Docker-Content-Digest")
    else:
        raise Exception(f"Failed to get digest: {response.text}")


  
def getDigestFromGithub(owner, image, tag) -> str:
    """Retrieves the latest digest for a Docker image from GHCR (Github Container Registry)."""
    digest = ""
    try:
        auth_url = f"https://ghcr.io/token?scope=repository:{owner}/{image}:pull"
        response_token = requests.get(auth_url)
        if response_token.status_code == 200:
            token = response_token.json().get("token")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error: {e}")
        return digest
    manifest_url = f"https://ghcr.io/v2/{owner}/{image}/manifests/{tag}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.docker.distribution.manifest.v2+json"
    }
    try:
        response = requests.head(manifest_url, headers=headers)
        if response.status_code == 200:
            return response.headers.get("Docker-Content-Digest")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error: {e}")
        return digest


def getDigestFromGitlab(owner, image, tag) -> str:
    """Fetch the image digest from GitLab Hub."""
    digest = ""
    manifest_url = f"https://registry.gitlab.com/v2/{owner}/{image}/manifests/{tag}"
    headers = {
        "Accept": "application/vnd.docker.distribution.manifest.v2+json"
    }
    try:
        response = requests.get(manifest_url, headers=headers, timeout=10)
        if response.status_code == 200:
            digest = response.headers.get("Docker-Content-Digest")
        return digest
    except requests.exceptions.RequestException as e:
        logger.error(f"Error: {e}")
        return digest


def getDigestFromDocker(owner, image, tag) -> str:
    """Retrieves the latest digest for a Docker image from HUB (Docker Hub)."""
    digest = ""
    auth_url = f"https://auth.docker.io/token"
    auth_params = {
        "service": "registry.docker.io",
        "scope": f"repository:{owner}/{image}:pull"
    }
    try:
        auth_response = requests.get(auth_url, params=auth_params)
        if auth_response.status_code == 200:
            token = auth_response.json().get("token")
        else:
            return digest
        manifest_url = f"https://registry-1.docker.io/v2/{owner}/{image}/manifests/{tag}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.docker.distribution.manifest.v2+json"
        }
        manifest_response = requests.get(manifest_url, headers=headers)
        if manifest_response.status_code == 200:
            return manifest_response.headers.get("Docker-Content-Digest")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error: {e}")
        return digest


def watchDigest():
    """Checks for outdated Docker images by comparing local digests with remote ones."""
    global old_list
    new_list = result = []
    current_time = datetime.now()
    for dockerdata in getDockerData():
        local_digest, source, owner, image, tag = dockerdata.split()
        if source in {"docker.io", "ghcr.io"}:
            digest = (getDigestFromDocker(owner, image, tag) if source in {"docker.io", "registry."} else getDigestFromGithub(owner, image, tag))
        elif source == "registry.gitlab.com":
            digest = getDigestFromGitlab(owner, image, tag)
        elif source == "registry.digitalocean.com":
            continue
        elif source.startswith(("registry.", "docker.io")):
            digest = getDigestFromDocker(owner, image, tag)
        else:
            continue
        if digest and digest != local_digest:
            new_list.append(f"{orange_dot} *{owner}/{image}*: outdated!\n")
    if new_list:
        if len(new_list) >= len(old_list):
            result = [item for item in new_list if item not in old_list]
    old_list = new_list
    with open(file_db, "w") as file:
        file.writelines(old_list)
    if result:
        SendMessage(f"{header_message}{''.join(result)}")
        logger.info(f"{''.join(result).replace(orange_dot, '').replace('*', '').strip()}")
    else:
        logger.info("All images are completely up to date!")
    new_time = current_time + timedelta(minutes=hour_repeat*60)
    logger.info(f"Scheduled next run: {new_time.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    """Load configuration and initialize monitoring"""
    docker_info = getDockerInfo()
    node_name = docker_info["node_name"]
    old_list = []
    config_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.json")
    file_db = os.path.join(os.path.dirname(os.path.realpath(__file__)), "data.db")
    if os.path.exists(file_db):
        with open(file_db, "r") as file:
            old_list.extend(file.readlines())
    dots = {"orange": "\U0001F7E0", "green": "\U0001F7E2", "red": "\U0001F534", "yellow": "\U0001F7E1", "purple": "\U0001F7E3", "brown": "\U0001F7E4"}
    square_dots = {"orange": "\U0001F7E7", "green": "\U0001F7E9", "red": "\U0001F7E5", "yellow": "\U0001F7E8", "purple": "\U0001F7EA", "brown": "\U0001F7EB"}
    header_message = f"*{node_name}* (.digest)\n"
    monitoring_message = f"- docker engine: {docker_info['docker_version']},\n"
    if os.path.exists(config_file):
        with open(config_file, "r") as file:
            config_json = json.loads(file.read())
        try:
            startup_message = config_json.get("STARTUP_MESSAGE", True)
            default_dot_style = config_json.get("DEFAULT_DOT_STYLE", True)
            hour_repeat = max(int(config_json.get("HOUR_REPEAT", 1)), 1)
        except (json.JSONDecodeError, ValueError, TypeError, KeyError):
            startup_message, default_dot_style = True, True
            hour_repeat = 2
            logger.error("Error or incorrect settings in config.json. Default settings will be used.")
        if not default_dot_style:
            dots = square_dots
        orange_dot, green_dot, red_dot, yellow_dot = dots["orange"], dots["green"], dots["red"], dots["yellow"]
        no_messaging_keys = ["GITHUB_PAT", "STARTUP_MESSAGE", "DEFAULT_DOT_STYLE", "HOUR_REPEAT"]
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
            f"- polling period: {hour_repeat} hours."
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
@repeat(every(hour_repeat).hours)
def RepeatCheck():
    watchDigest()

while True:
    run_pending()
    time.sleep(1)
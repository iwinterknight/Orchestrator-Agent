import logging
import os
import re
import sys

from path_utils import get_project_root

sys.path.insert(0, str(get_project_root()))

import requests
from starlette.websockets import WebSocketState
from websocket import WebSocket


async def send_websocket_update(websocket: WebSocket, message: str, message_type="update"):
    if websocket and not websocket.client_state == WebSocketState.DISCONNECTED:
        if message_type == "progress":
            await websocket.send_text(f"Progress : {message}")
        elif message_type == "update":
            await websocket.send_text(f"Update : {message}")
        elif message_type == "priority":
            await websocket.send_text(f"Priority : {message}")
    else:
        if message_type == "progress":
            print(f"Progress : {message}")
        elif message_type == "update":
            print(f"Update : {message}")
        elif message_type == "priority":
            print(f"Priority : {message}")


def initialize_logging(logger):
    logdir = str(get_project_root() / "ai-agent-package" / "logs")

    # Create handlers for different log levels
    error_handler = logging.FileHandler(os.path.join(logdir, "errors.log"))
    error_handler.setLevel(logging.ERROR)

    debug_handler = logging.FileHandler(os.path.join(logdir, "debug.log"))
    debug_handler.setLevel(logging.DEBUG)

    info_handler = logging.FileHandler(os.path.join(logdir, "info.log"))
    info_handler.setLevel(logging.INFO)

    # Create formatters and add them to the handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    error_handler.setFormatter(formatter)
    debug_handler.setFormatter(formatter)
    info_handler.setFormatter(formatter)

    # Add handlers to the logger
    logger.addHandler(error_handler)
    logger.addHandler(debug_handler)
    logger.addHandler(info_handler)


def clean_attribute_name(name):
    """Remove leading/trailing periods, question marks, and special characters."""
    return re.sub(r'^[\.\?\s]+|[\.\?\s]+$', '', name.strip())


def make_fastapi_request(url, logger, method="GET", **kwargs):
    logger.info("Making request to llm api.")
    if method == "GET":
        response = requests.get(url, **kwargs)
    elif method == "POST":
        response = requests.post(url, **kwargs)
    elif method == "PUT":
        response = requests.put(url, **kwargs)
    elif method == "DELETE":
        response = requests.delete(url, **kwargs)
    else:
        logger.error("Invalid HTTP method.")
    response.raise_for_status()
    logger.info("Received llm response for article class inference.")
    return response.json()


def dedupe_by_attribute(listofdicts: list, attribute: str):
    seen = set()
    unique_dicts = []
    for d in listofdicts:
        sid = d.get(attribute)
        if sid not in seen:
            unique_dicts.append(d)
            seen.add(sid)
    return unique_dicts


def remove_absent_values(d: dict):
    absent_values = {"not available", "nan", "na", "null", "none", ""}
    return {
        k: v for k, v in d.items()
        if not (isinstance(v, str) and v.strip().lower() in absent_values)
    }

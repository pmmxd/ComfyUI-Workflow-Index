import json
import os
import threading
import time
from urllib.parse import urlparse

from aiohttp import web
from server import PromptServer


WEB_DIRECTORY = "./web"
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

WORKFLOWS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "user", "default", "workflows")
)
FAVORITES_PATH = os.path.join(WORKFLOWS_DIR, "_个人精品.json")
FAVORITES_LOCK = threading.Lock()
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _cors_origin(request):
    origin = request.headers.get("Origin", "")
    if not origin:
        return None
    try:
        parsed = urlparse(origin)
        if parsed.scheme in {"http", "https"} and parsed.hostname in LOOPBACK_HOSTS:
            return origin
    except ValueError:
        pass
    return None


def _with_cors(response, request):
    origin = _cors_origin(request)
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        response.headers["Vary"] = "Origin"
    return response


def _normalize_favorites(values):
    favorites = []
    seen = set()
    for value in values:
        if not isinstance(value, str):
            continue
        path = value.strip().replace("\\", "/").lstrip("/")
        segments = path.split("/")
        if (
            not path
            or len(path) > 500
            or any(segment in {"", ".", ".."} for segment in segments)
            or path in seen
        ):
            continue
        seen.add(path)
        favorites.append(path)
        if len(favorites) >= 5000:
            break
    return favorites


def _read_favorites():
    if not os.path.exists(FAVORITES_PATH):
        return {"updatedAt": 0, "favorites": []}
    with open(FAVORITES_PATH, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("个人精品数据格式无效")
    return {
        "updatedAt": max(0, int(data.get("updatedAt") or 0)),
        "favorites": _normalize_favorites(data.get("favorites") or []),
    }


def _write_favorites(data):
    os.makedirs(WORKFLOWS_DIR, exist_ok=True)
    temporary_path = FAVORITES_PATH + ".tmp"
    with open(temporary_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temporary_path, FAVORITES_PATH)


@PromptServer.instance.routes.options("/dapao/workflow-favorites")
async def workflow_favorites_options(request):
    return _with_cors(web.Response(status=204), request)


@PromptServer.instance.routes.get("/dapao/workflow-favorites")
async def workflow_favorites_get(request):
    try:
        with FAVORITES_LOCK:
            data = _read_favorites()
        return _with_cors(web.json_response(data), request)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return _with_cors(
            web.json_response({"error": str(error)}, status=500),
            request,
        )


@PromptServer.instance.routes.post("/dapao/workflow-favorites")
async def workflow_favorites_post(request):
    try:
        payload = await request.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("favorites"), list):
            raise ValueError("收藏数据格式无效")
        data = {
            "updatedAt": int(payload.get("updatedAt") or time.time() * 1000),
            "favorites": _normalize_favorites(payload["favorites"]),
        }
        with FAVORITES_LOCK:
            _write_favorites(data)
        return _with_cors(web.json_response(data), request)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        return _with_cors(
            web.json_response({"error": str(error)}, status=400),
            request,
        )


__all__ = ["WEB_DIRECTORY", "NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

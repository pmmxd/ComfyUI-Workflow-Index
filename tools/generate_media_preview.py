# -*- coding: utf-8 -*-
"""Build a read-only gallery for images, videos, and audio in ComfyUI output."""

from __future__ import annotations

import datetime
import hashlib
import html
import json
import os
import subprocess
import urllib.parse
import warnings
from collections import Counter, defaultdict

import cv2
from PIL import Image


def env_path(name, default=""):
    value = os.environ.get(name, "").strip().strip('"')
    if not value:
        value = default.strip().strip('"')
    if not value:
        return ""
    return os.path.abspath(os.path.expandvars(os.path.expanduser(value)))


ROOT = env_path("COMFYUI_ROOT")
if not ROOT:
    raise SystemExit("请先设置 COMFYUI_ROOT，指向 ComfyUI 根目录。")

OUTPUT = os.path.join(ROOT, "ComfyUI", "output")
if not os.path.isdir(OUTPUT) and os.path.basename(ROOT).lower() == "comfyui":
    OUTPUT = os.path.join(ROOT, "output")
WORKFLOWS = env_path(
    "COMFYUI_WORKFLOWS_DIR",
    os.path.join(ROOT, "user", "default", "workflows"),
)
CACHE = os.path.join(WORKFLOWS, "_媒体预览缓存")
THUMBS = os.path.join(CACHE, "thumbnails")
PAGE = os.path.join(WORKFLOWS, "媒体预览测试.html")
FFPROBE = env_path("FFPROBE_PATH") or "ffprobe"
WORKFLOW_INDEX = os.path.join(WORKFLOWS, "工作流总索引.csv")

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv"}
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".ogg", ".m4a"}


MEDIA_BASE = "_媒体预览缓存/media"


def file_url(relative_path: str) -> str:
    quoted = "/".join(
        urllib.parse.quote(part) for part in relative_path.replace("\\", "/").split("/")
    )
    return f"{MEDIA_BASE}/{quoted}"


def thumbnail_name(relative_path: str) -> str:
    digest = hashlib.sha1(relative_path.encode("utf-8")).hexdigest()
    return f"{digest}.webp"


def save_thumbnail(image: Image.Image, destination: str) -> None:
    image.thumbnail((640, 480))
    image.convert("RGB").save(destination, "WEBP", quality=78, method=5)


def image_info(path: str) -> tuple[dict, list[str], dict | None]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with Image.open(path) as image:
            workflow = None
            raw_workflow = image.info.get("workflow")
            if raw_workflow:
                try:
                    workflow = (
                        json.loads(raw_workflow)
                        if isinstance(raw_workflow, str)
                        else raw_workflow
                    )
                except (TypeError, json.JSONDecodeError):
                    workflow = None
            return (
                {"width": image.width, "height": image.height},
                sorted(image.info.keys()),
                workflow if isinstance(workflow, dict) else None,
            )


def video_info(path: str) -> tuple[dict, list[str], dict | None]:
    metadata_keys: list[str] = []
    info: dict = {}
    workflow = None
    try:
        completed = subprocess.run(
            [
                FFPROBE,
                "-v",
                "error",
                "-show_entries",
                "format_tags:stream=codec_type,width,height,duration",
                "-of",
                "json",
                path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        payload = json.loads(completed.stdout or "{}")
        tags = (payload.get("format") or {}).get("tags", {})
        metadata_keys = sorted(tags.keys())
        if tags.get("workflow"):
            try:
                parsed = json.loads(tags["workflow"])
                workflow = parsed if isinstance(parsed, dict) else None
            except (TypeError, json.JSONDecodeError):
                workflow = None
        for stream in payload.get("streams") or []:
            if stream.get("codec_type") == "video":
                info["width"] = stream.get("width")
                info["height"] = stream.get("height")
            try:
                if float(stream.get("duration", 0)) > 0:
                    info["duration"] = round(float(stream["duration"]), 2)
            except (TypeError, ValueError):
                pass
    except Exception as error:
        info["probe_error"] = str(error)
    return info, metadata_keys, workflow


def video_thumbnail(path: str, destination: str) -> bool:
    capture = cv2.VideoCapture(path)
    try:
        fps = capture.get(cv2.CAP_PROP_FPS) or 24
        capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(fps)))
        ok, frame = capture.read()
        if not ok:
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = capture.read()
        if not ok:
            return False
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        save_thumbnail(Image.fromarray(frame), destination)
        return True
    finally:
        capture.release()


def all_workflow_nodes(workflow: dict) -> list[dict]:
    nodes = list(workflow.get("nodes") or [])
    for subgraph in (workflow.get("definitions") or {}).get("subgraphs", []) or []:
        if isinstance(subgraph, dict):
            nodes.extend(subgraph.get("nodes") or [])
    return [node for node in nodes if isinstance(node, dict)]


def workflow_signature(workflow: dict) -> str:
    nodes = all_workflow_nodes(workflow)
    node_by_id = {node.get("id"): node for node in nodes}
    node_types = Counter(node.get("type") for node in nodes if node.get("type"))
    edges = []
    link_sets = [workflow.get("links") or []]
    link_sets.extend(
        subgraph.get("links") or []
        for subgraph in (workflow.get("definitions") or {}).get("subgraphs", []) or []
        if isinstance(subgraph, dict)
    )
    for links in link_sets:
        for link in links:
            if not isinstance(link, list) or len(link) < 6:
                continue
            _, origin_id, origin_slot, target_id, target_slot, link_type = link[:6]
            origin = node_by_id.get(origin_id)
            target = node_by_id.get(target_id)
            if origin and target:
                edges.append(
                    (
                        origin.get("type"),
                        origin_slot,
                        target.get("type"),
                        target_slot,
                        link_type,
                    )
                )
    raw = json.dumps(
        [sorted(node_types.items()), sorted(edges, key=str)],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_workflow_maps() -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    import csv

    by_id: dict[str, list[dict]] = defaultdict(list)
    by_signature: dict[str, list[dict]] = defaultdict(list)
    with open(WORKFLOW_INDEX, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                with open(row["完整硬盘路径"], encoding="utf-8-sig") as workflow_file:
                    workflow = json.load(workflow_file)
            except (KeyError, OSError, json.JSONDecodeError):
                continue
            if workflow.get("id"):
                by_id[str(workflow["id"])].append(row)
            by_signature[workflow_signature(workflow)].append(row)
    return by_id, by_signature


def choose_workflow(matches: list[dict]) -> dict:
    return sorted(
        matches,
        key=lambda row: (
            row.get("是否旧版") == "是",
            -int(row.get("评级") or 0),
            row.get("相对路径", "").count("\\"),
            len(row.get("相对路径", "")),
            row.get("相对路径", ""),
        ),
    )[0]


def match_workflow(
    embedded_workflow: dict | None,
    by_id: dict[str, list[dict]],
    by_signature: dict[str, list[dict]],
) -> tuple[dict | None, str]:
    if not isinstance(embedded_workflow, dict):
        return None, ""
    workflow_id = str(embedded_workflow.get("id") or "")
    if workflow_id and workflow_id in by_id:
        return choose_workflow(by_id[workflow_id]), "id"
    matches = by_signature.get(workflow_signature(embedded_workflow), [])
    if matches:
        return choose_workflow(matches), "topology"
    return None, ""


def build_items() -> list[dict]:
    items: list[dict] = []
    by_id, by_signature = load_workflow_maps()
    os.makedirs(THUMBS, exist_ok=True)
    for root, _, files in os.walk(OUTPUT):
        for filename in files:
            path = os.path.join(root, filename)
            ext = os.path.splitext(filename)[1].lower()
            if ext in IMAGE_EXTS:
                kind = "image"
            elif ext in VIDEO_EXTS:
                kind = "video"
            elif ext in AUDIO_EXTS:
                kind = "audio"
            else:
                continue

            relative_path = os.path.relpath(path, OUTPUT).replace(os.sep, "/")
            stat = os.stat(path)
            thumb_name = thumbnail_name(relative_path)
            thumb_path = os.path.join(THUMBS, thumb_name)
            info: dict = {}
            metadata_keys: list[str] = []
            embedded_workflow = None

            if kind == "image":
                try:
                    info, metadata_keys, embedded_workflow = image_info(path)
                    with Image.open(path) as image:
                        save_thumbnail(image, thumb_path)
                except Exception as error:
                    info["error"] = str(error)
            elif kind == "video":
                info, metadata_keys, embedded_workflow = video_info(path)
                if not video_thumbnail(path, thumb_path):
                    thumb_name = ""

            workflow_row, match_type = match_workflow(
                embedded_workflow, by_id, by_signature
            )

            items.append(
                {
                    "name": filename,
                    "relative": relative_path,
                    "kind": kind,
                    "url": file_url(relative_path),
                    "thumb": (
                        f"_媒体预览缓存/thumbnails/{thumb_name}"
                        if thumb_name and os.path.exists(thumb_path)
                        else ""
                    ),
                    "size": stat.st_size,
                    "modified": datetime.datetime.fromtimestamp(
                        stat.st_mtime
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                    "dimensions": (
                        f"{info.get('width')}x{info.get('height')}"
                        if info.get("width") and info.get("height")
                        else ""
                    ),
                    "duration": info.get("duration"),
                    "metadata": metadata_keys,
                    "hasWorkflowMetadata": (
                        "workflow" in metadata_keys or "prompt" in metadata_keys
                    ),
                    "workflowRelative": (
                        workflow_row.get("相对路径", "").replace("\\", "/")
                        if workflow_row
                        else ""
                    ),
                    "workflowName": (
                        workflow_row.get("工作流名称", "") if workflow_row else ""
                    ),
                    "workflowMatch": match_type,
                }
            )
    items.sort(key=lambda item: item["modified"], reverse=True)
    return items


def render(items: list[dict]) -> str:
    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    payload = json.dumps(items, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>ComfyUI 输出媒体预览测试</title>
  <style>
    :root {{
      --bg:#101714; --panel:#17221d; --card:#1c2a23; --line:#304239;
      --text:#eef5f0; --muted:#a5b6ac; --accent:#60c68c; --warm:#e0a14c;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0;background:var(--bg);color:var(--text);font:14px/1.5 "Segoe UI","Microsoft YaHei",sans-serif; }}
    header {{ padding:18px 22px;border-bottom:1px solid var(--line);display:flex;gap:18px;align-items:center;justify-content:space-between;flex-wrap:wrap; }}
    h1 {{ margin:0;font-size:20px; }}
    .meta {{ color:var(--muted);font-size:12px; }}
    .filters {{ display:flex;gap:8px;flex-wrap:wrap;padding:14px 22px;background:var(--panel);position:sticky;top:0;z-index:4;border-bottom:1px solid var(--line); }}
    input,select,button {{ font:inherit;border:1px solid var(--line);border-radius:6px;background:#0e1512;color:var(--text);min-height:34px;padding:0 10px; }}
    button {{ cursor:pointer; }}
    button.active {{ border-color:var(--accent);color:var(--accent); }}
    .search {{ flex:1 1 260px; }}
    main {{ padding:18px 22px 40px; }}
    .summary {{ color:var(--muted);margin-bottom:14px; }}
    .grid {{ display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px; }}
    .card {{ border:1px solid var(--line);background:var(--card);border-radius:8px;overflow:hidden;cursor:pointer;min-width:0; }}
    .thumb {{ aspect-ratio:4/3;background:#0b110e;display:flex;align-items:center;justify-content:center;overflow:hidden;position:relative; }}
    .thumb img {{ width:100%;height:100%;object-fit:cover;display:block; }}
    .audio {{ color:var(--warm);font-size:52px; }}
    .kind {{ position:absolute;right:8px;top:8px;padding:2px 7px;border-radius:5px;background:#07100bb8;font-size:11px;text-transform:uppercase; }}
    .card-body {{ padding:10px; }}
    .name {{ font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }}
    .sub {{ margin-top:4px;color:var(--muted);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }}
    .badge {{ display:inline-block;margin-top:7px;padding:2px 6px;border:1px solid var(--line);border-radius:4px;color:var(--muted);font-size:10px; }}
    .badge.ok {{ color:var(--accent);border-color:#315d46; }}
    .modal {{ position:fixed;inset:0;background:#050907e8;display:none;align-items:center;justify-content:center;padding:24px;z-index:20; }}
    .modal.open {{ display:flex; }}
    .modal-box {{ width:min(1200px,96vw);max-height:94vh;background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden;display:flex;flex-direction:column; }}
    .modal-head {{ padding:12px 16px;display:flex;justify-content:space-between;gap:12px;align-items:center;border-bottom:1px solid var(--line); }}
    .modal-title {{ min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }}
    .modal-body {{ min-height:0;overflow:auto;display:flex;justify-content:center;align-items:center;background:#080d0b; }}
    .modal-body img,.modal-body video {{ max-width:100%;max-height:78vh;display:block; }}
    .modal-body audio {{ width:min(720px,90%); }}
    .close {{ width:34px;height:34px;padding:0; }}
    .empty {{ color:var(--muted);padding:60px 0;text-align:center; }}
    @media (max-width:700px) {{ header,main,.filters {{ padding-left:10px;padding-right:10px; }} .grid {{ grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px; }} }}
  </style>
</head>
<body>
  <header>
    <div><h1>ComfyUI 输出媒体预览测试</h1><div class="meta">只读扫描 output，生成时间 {html.escape(generated_at)}</div></div>
    <div class="meta">原文件不移动、不修改</div>
  </header>
  <section class="filters">
    <input id="search" class="search" type="search" placeholder="搜索文件名或路径">
    <button type="button" data-kind="" class="active">全部</button>
    <button type="button" data-kind="image">图片</button>
    <button type="button" data-kind="video">视频</button>
    <button type="button" data-kind="audio">音频</button>
    <label class="meta"><input id="metadataOnly" type="checkbox"> 仅看带工作流元数据</label>
  </section>
  <main>
    <div class="summary" id="summary"></div>
    <div class="grid" id="grid"></div>
    <div class="empty" id="empty" hidden>没有匹配的媒体</div>
  </main>
  <div class="modal" id="modal">
    <div class="modal-box">
      <div class="modal-head"><div class="modal-title" id="modalTitle"></div><button class="close" id="closeModal" type="button">×</button></div>
      <div class="modal-body" id="modalBody"></div>
    </div>
  </div>
  <script>
    const ITEMS = {payload};
    const state = {{ kind:"", query:"", metadataOnly:false }};
    const grid = document.getElementById("grid");
    const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, ch => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[ch]));
    const formatSize = bytes => bytes >= 1024**2 ? (bytes/1024**2).toFixed(1)+" MB" : (bytes/1024).toFixed(1)+" KB";
    function filtered() {{
      const q=state.query.toLocaleLowerCase();
      return ITEMS.filter(item => (!state.kind || item.kind===state.kind)
        && (!state.metadataOnly || item.hasWorkflowMetadata)
        && (!q || (item.name+" "+item.relative).toLocaleLowerCase().includes(q)));
    }}
    function render() {{
      const items=filtered();
      document.getElementById("summary").textContent=`显示 ${{items.length}} / ${{ITEMS.length}} 个媒体文件`;
      document.getElementById("empty").hidden=items.length>0;
      grid.innerHTML=items.map((item,index) => `<article class="card" data-open="${{ITEMS.indexOf(item)}}">
        <div class="thumb">${{item.thumb?`<img loading="lazy" src="${{escapeHtml(item.thumb)}}" alt="">`:`<div class="audio">♪</div>`}}<span class="kind">${{escapeHtml(item.kind)}}</span></div>
        <div class="card-body"><div class="name" title="${{escapeHtml(item.relative)}}">${{escapeHtml(item.name)}}</div>
        <div class="sub">${{escapeHtml(item.modified)}} · ${{escapeHtml(formatSize(item.size))}}${{item.dimensions?" · "+escapeHtml(item.dimensions):""}}${{item.duration?" · "+item.duration+"s":""}}</div>
        <span class="badge ${{item.hasWorkflowMetadata?"ok":""}}">${{item.hasWorkflowMetadata?"含工作流元数据":"无工作流元数据"}}</span>
        ${{item.workflowName?`<span class="badge ok" title="已关联工作流">${{escapeHtml(item.workflowName)}}</span>`:""}}</div>
      </article>`).join("");
    }}
    function openItem(index) {{
      const item=ITEMS[index]; document.getElementById("modalTitle").textContent=item.relative;
      const body=document.getElementById("modalBody");
      if(item.kind==="image") body.innerHTML=`<img src="${{escapeHtml(item.url)}}" alt="">`;
      else if(item.kind==="video") body.innerHTML=`<video controls autoplay preload="metadata" src="${{escapeHtml(item.url)}}" ${{item.thumb?`poster="${{escapeHtml(item.thumb)}}"`:""}}></video>`;
      else body.innerHTML=`<audio controls autoplay src="${{escapeHtml(item.url)}}"></audio>`;
      document.getElementById("modal").classList.add("open");
    }}
    document.addEventListener("click", event => {{
      const kind=event.target.closest("[data-kind]"); if(kind){{ state.kind=kind.dataset.kind; document.querySelectorAll("[data-kind]").forEach(b=>b.classList.toggle("active",b===kind)); render(); return; }}
      const card=event.target.closest("[data-open]"); if(card) openItem(Number(card.dataset.open));
    }});
    document.getElementById("modal").addEventListener("click", event => {{ if(event.target.id==="modal"||event.target.id==="closeModal") {{ document.getElementById("modal").classList.remove("open"); document.getElementById("modalBody").innerHTML=""; }} }});
    document.getElementById("search").addEventListener("input", event => {{ state.query=event.target.value; render(); }});
    document.getElementById("metadataOnly").addEventListener("change", event => {{ state.metadataOnly=event.target.checked; render(); }});
    render();
  </script>
</body>
</html>"""


def main() -> None:
    os.makedirs(CACHE, exist_ok=True)
    items = build_items()
    page = render(items)
    with open(os.path.join(CACHE, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(items, handle, ensure_ascii=False, indent=2)
    with open(PAGE, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(page)
    print(f"items={len(items)}")
    print(f"page={PAGE}")


if __name__ == "__main__":
    main()

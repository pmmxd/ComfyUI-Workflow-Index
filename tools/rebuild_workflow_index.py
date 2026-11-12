# -*- coding: utf-8 -*-
"""Rebuild searchable indexes for the current ComfyUI workflow directory."""

import collections
import csv
import datetime
import hashlib
import json
import os
import re


def env_path(name, default=""):
    value = os.environ.get(name, "").strip().strip('"')
    if not value:
        value = default.strip().strip('"')
    if not value:
        return ""
    return os.path.abspath(os.path.expandvars(os.path.expanduser(value)))


COMFYUI_ROOT = env_path("COMFYUI_ROOT")
if not COMFYUI_ROOT:
    raise SystemExit("请先设置 COMFYUI_ROOT，指向 ComfyUI 根目录。")

WF = env_path(
    "COMFYUI_WORKFLOWS_DIR",
    os.path.join(COMFYUI_ROOT, "user", "default", "workflows"),
)
E_MODELS_ROOT = env_path(
    "COMFYUI_MODELS_DIR",
    os.path.join(COMFYUI_ROOT, "models"),
)
EXTRA_MODEL_ROOTS = [
    env_path(value)
    for value in os.environ.get("EXTRA_MODEL_DIRS", "").split(os.pathsep)
    if value.strip()
]
CONTROLNET_AUX_ROOT = env_path(
    "CONTROLNET_AUX_ROOT",
    os.path.join(
        COMFYUI_ROOT,
        "custom_nodes",
        "comfyui_controlnet_aux",
        "ckpts",
    ),
)
MODEL_ROOTS = (
    ("E本机", E_MODELS_ROOT),
    *[
        ("G备份", root)
        for root in EXTRA_MODEL_ROOTS
        if os.path.isdir(root)
    ],
    *(
        [("DWPose", CONTROLNET_AUX_ROOT)]
        if os.path.isdir(CONTROLNET_AUX_ROOT)
        else []
    ),
)
MODEL_EXTS = (".safetensors", ".ckpt", ".pth", ".pt", ".gguf", ".bin", ".onnx")
MIGRATION_PATH = os.path.join(WF, "模型迁移清单.json")
LEGACY_NAMES = ("_旧版", "_半成品", "_需补模型")
ARCHIVE_NAMES = ("旧版", "半成品", "需补模型")
UI_NODES = {
    "MarkdownNote",
    "Note",
    "Note Plus (mtb)",
    "孤海注释",
    "Reroute",
    "Label (rgthree)",
    "Fast Groups Bypasser (rgthree)",
    "GetNode",
    "SetNode",
}
API_RE = re.compile(
    r"DapaoGPT|DapaoAPI|DapaoSeedance|DapaoWan30|DapaoDetailFlow|RH_",
    re.I,
)
RENAME_MAP_PATH = os.path.join(WF, "_工具脚本", "rename_current_workflows.json")


def read_workflow(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    nodes = list(data.get("nodes") or [])
    definitions = data.get("definitions") or {}
    for subgraph in definitions.get("subgraphs") or []:
        if isinstance(subgraph, dict):
            nodes.extend(subgraph.get("nodes") or [])
    return nodes


def dated_name(name):
    match = re.search(r"(?<!\d)(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})(?!\d)", name)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    match = re.search(r"(?<!\d)(2[3-9])[-_.](\d{1,2})[-_.](\d{1,2})(?!\d)", name)
    if match:
        return f"20{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return ""


def model_family(text):
    patterns = (
        ("MiniMax Music3", r"minimax[_ -]?music"),
        ("MiniMax H3", r"minimax"),
        ("Wan / SCAIL / Bernini", r"scail|wan2|wan_2|bernini|umt5"),
        ("Krea2", r"krea2|moodyKrea"),
        ("FLUX.3 Klein", r"flux3|flux[_ -]?3"),
        ("FLUX.2 Klein", r"flux[_ -]?2|klein|f2k_"),
        ("Z-Image", r"z[_ -]?image|zimage|zit_"),
        ("Qwen Image", r"qwen.{0,20}image|qwen_image|qwenimage|qwen3vl|qwen-rapid"),
        ("SeedVR2", r"seedvr"),
        ("FlashVSR", r"flashvsr"),
        ("IndexTTS2", r"indextts"),
        ("SAM3", r"sam3"),
        ("FLUX.1", r"flux1|flux\.1|t5xxl"),
        ("SDXL", r"sdxl|dreamshaper|juggernaut"),
        ("SD1.5", r"sd15|sd1\.5|control_v11|majicmix|revanimated"),
    )
    for label, pattern in patterns:
        if re.search(pattern, text, re.I):
            return label
    return "通用 / API"


def duplicate_rank(rel):
    parts = rel.split(os.sep)
    if parts and parts[0] == "_归档":
        return (6, len(rel))
    if "_12G" in rel or "00-12G首选" in rel:
        return (0, len(rel))
    if parts[0] == "00-★★★★★精品":
        return (1, len(rel))
    if any(part in LEGACY_NAMES for part in parts):
        return (5, len(rel))
    return (2, len(rel))


def workflow_features(parts, types):
    features = []
    if any(name in types for name in ("KSampler", "KSamplerAdvanced", "SamplerCustomAdvanced")):
        features.append("生成/采样")
    if any("QwenImage21Cache" == name or name == "TextEncodeQwenImage21" for name in types):
        features.append("Qwen指令编辑")
    if any("Krea2" in name for name in types):
        features.append("Krea2风格")
    if any("SeedVR2" in name or name == "UpscaleModelLoader" for name in types):
        features.append("高清放大")
    if any("SAM3" in name or "Matting" in name for name in types):
        features.append("抠图/分割")
    if any("MiniMaxH3" in name or "MiniMax" in name for name in types):
        features.append("MiniMax视频/音频")
    if any("SaveAudio" in name for name in types):
        features.append("音频输出")
    if any("VideoCombine" in name or name == "CreateVideo" for name in types):
        features.append("视频合成")
    if any("Dapao_Llama" in name or "TextGenerateLTX2Prompt" in name for name in types):
        features.append("LLM提示词")
    if any("ControlNet" in name for name in types):
        features.append("ControlNet")
    if any("Lora" in name for name in types):
        features.append("LoRA")
    if any("FaceRestore" in name for name in types):
        features.append("人脸修复")
    if any("Mask" in name or "sam3" in name.lower() for name in types):
        features.append("遮罩")
    if any(API_RE.search(name) for name in types):
        features.append("API")
    if parts and parts[0] == "_场景整合工作流":
        features.append("场景一体")
    return " | ".join(dict.fromkeys(features))


def priority(rel):
    parts = rel.split(os.sep)
    if parts[0] == "_场景整合工作流":
        return "场景主流程"
    if parts[0] == "FLUX3工作流":
        return "FLUX3专题"
    if "00-12G首选" in rel:
        return "12G首选"
    if parts[0] == "00-★★★★★精品":
        return "精品展示"
    if parts[0] == "_归档":
        return "归档"
    return "分类流程"


MODERN_FAMILIES = {
    "Qwen Image",
    "FLUX.2 Klein",
    "FLUX.3 Klein",
    "Z-Image",
    "Krea2",
    "MiniMax H3",
    "MiniMax Music3",
    "SeedVR2",
    "FlashVSR",
    "IndexTTS2",
    "SAM3",
}


def rating_for(row):
    priority_name = row["优先级"]
    status = row["状态"]
    if priority_name == "12G首选":
        return 5
    if priority_name == "场景主流程":
        if status == "本地可用":
            return 5
        if status == "需API":
            return 4
        return 2
    if priority_name == "FLUX3专题":
        if status == "本地可用":
            return 5
        return 2
    if priority_name == "精品展示":
        if status == "本地可用":
            return 4
        if status == "需API":
            return 3
        return 2
    if priority_name == "分类流程":
        if status == "本地可用" and row["模型族"] in MODERN_FAMILIES:
            return 4
        if status == "本地可用":
            return 3
        if status == "需API":
            return 2
        return 1
    return 1


def recommendation_for(rating):
    if rating >= 4:
        return "推荐"
    if rating == 3:
        return "备选"
    return "不推荐"


def recommendation_tags(row, rating):
    tags = []
    if rating == 5:
        tags.append("首选")
    elif rating == 4:
        tags.append("推荐")
    elif rating == 3:
        tags.append("备选")
    else:
        tags.append("不推荐")
    tags.append(row["优先级"])
    if row["状态"] == "本地可用":
        tags.append("本地可用")
    elif row["状态"] == "需API":
        tags.append("需API")
    elif row["状态"] == "需补模型":
        tags.append("需补模型")
    if row["模型族"] in MODERN_FAMILIES:
        tags.append("最新模型")
    if "高清放大" in row["核心功能"]:
        tags.append("含放大")
    if "LLM提示词" in row["核心功能"]:
        tags.append("提示词增强")
    if "ControlNet" in row["核心功能"]:
        tags.append("结构控制")
    if row["模型总大小GB"]:
        model_gb = float(row["模型总大小GB"])
        if model_gb >= 50:
            tags.append("重负载")
        elif model_gb <= 4:
            tags.append("轻量")
    steps = [int(value) for value in re.findall(r"\d+", row["采样步数"])]
    if steps and max(steps) <= 10:
        tags.append("快速")
    return " | ".join(dict.fromkeys(tags))


def rating_reason(row, rating):
    if rating == 5:
        return f"当前主力推荐：{row['优先级']}，{row['模型族']}，{row['核心功能']}"
    if rating == 4:
        return f"高质量可用流程：{row['优先级']}，{row['模型族']}"
    if rating == 3:
        return f"可用但非首选：{row['状态']}，{row['模型族']}"
    if rating == 2:
        return f"需要额外条件：{row['状态']}，建议作为备选"
    return "旧版或归档流程，不建议日常使用"


def main():
    clean_to_original = {}
    if os.path.exists(RENAME_MAP_PATH):
        with open(RENAME_MAP_PATH, "r", encoding="utf-8") as handle:
            rename_data = json.load(handle)
        clean_to_original = {
            clean: original
            for original, clean in (
                rename_data.get("original_to_clean") or {}
            ).items()
        }
    installed = collections.defaultdict(list)
    for source_label, models_root in MODEL_ROOTS:
        for root, _, files in os.walk(models_root):
            for name in files:
                if name.lower().endswith(MODEL_EXTS):
                    path = os.path.join(root, name)
                    installed[name.lower()].append(
                        (
                            source_label,
                            path,
                            os.path.relpath(path, models_root),
                        )
                    )
    installed_bases = set(installed)
    installed_sizes = {}
    for basename, paths in installed.items():
        installed_sizes[basename] = max(os.path.getsize(path) for _, path, _ in paths)

    rows = []
    model_usage = collections.defaultdict(list)
    for root, _, files in os.walk(WF):
        rel_dir = os.path.relpath(root, WF)
        if rel_dir.startswith("_工具脚本"):
            continue
        if rel_dir == "_媒体预览缓存" or rel_dir.startswith(
            "_媒体预览缓存" + os.sep
        ):
            continue
        for name in files:
            if not name.lower().endswith(".json"):
                continue
            if name.startswith("_"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, WF)
            raw = open(path, "rb").read()
            try:
                nodes = read_workflow(path)
            except (OSError, json.JSONDecodeError):
                nodes = []
            active_nodes = [
                node
                for node in nodes
                if isinstance(node, dict) and node.get("mode") not in (2, 4)
            ]
            types = {
                node.get("type")
                for node in active_nodes
                if isinstance(node.get("type"), str)
            }
            plugins = set()
            loaders = set()
            model_sources = set()
            models_missing = set()
            e_models = set()
            g_only_models = set()
            g_duplicate_models = set()
            model_size = 0
            sizes = []
            steps = []
            for node in active_nodes:
                props = node.get("properties")
                if not isinstance(props, dict):
                    props = {}
                for key in ("cnr_id", "aux_id"):
                    value = props.get(key)
                    if value and value not in ("comfy-core", "comfyui", "comfyui-core"):
                        plugins.add(str(value))
                for value in node.get("widgets_values") or []:
                    if not isinstance(value, str) or not value.lower().endswith(MODEL_EXTS):
                        continue
                    basename = os.path.basename(value.replace("\\", "/")).lower()
                    loaders.add(basename)
                    if basename not in installed_bases:
                        models_missing.add(basename)
                    else:
                        model_size += installed_sizes.get(basename, 0)
                        sources = {
                            source_label
                            for source_label, _, _ in installed[basename]
                        }
                        model_sources.update(sources)
                        has_e = bool(sources & {"E本机", "DWPose"})
                        has_g = "G备份" in sources
                        if has_e:
                            e_models.add(basename)
                            if has_g:
                                g_duplicate_models.add(basename)
                        elif has_g:
                            g_only_models.add(basename)
                node_type = node.get("type")
                widgets = node.get("widgets_values") or []
                if node_type in ("KSampler", "KSamplerAdvanced") and len(widgets) > 2:
                    value = widgets[2]
                    if isinstance(value, int) and 1 <= value <= 100:
                        steps.append(str(value))
                if node_type in ("EmptyLatentImage", "EmptySD3LatentImage") and len(widgets) >= 2:
                    sizes.append(f"{widgets[0]}x{widgets[1]}")
                if node_type == "ResolutionSelector" and len(widgets) >= 2:
                    sizes.append(f"{widgets[0]};{widgets[1]}MP")

            def has_type(*names):
                return any(name in types for name in names)

            input_media = []
            if has_type("LoadImage", "LoadImageMask"):
                input_media.append("图像")
            if has_type("LoadAudio", "VHS_LoadAudio"):
                input_media.append("音频")
            if has_type("LoadVideo", "VHS_LoadVideo", "LoadVideoUpload"):
                input_media.append("视频")
            output_media = []
            if any(
                name == "DapaoSafeSaveImage" or name.startswith("SaveImage")
                for name in types
            ) or has_type("PreviewImage"):
                output_media.append("图片")
            if any(
                name.startswith("SaveVideo")
                or name.startswith("PreviewVideo")
                or name.startswith("VideoCombine")
                for name in types
            ) or has_type("VHS_VideoCombine", "TESpeedVideoCombine", "CreateVideo"):
                output_media.append("视频")
            if any(
                name.startswith("SaveAudio") or name.startswith("PreviewAudio")
                for name in types
            ):
                output_media.append("音频")

            parts = rel.split(os.sep)
            legacy = parts[0] == "_归档" or any(part in LEGACY_NAMES for part in parts)
            api_nodes = sorted(type_name for type_name in types if API_RE.search(type_name))
            family = model_family(" ".join([name, *sorted(loaders), *sorted(types)]))
            date = dated_name(name)
            if not date:
                date = datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()
            moved_at = datetime.datetime.fromtimestamp(
                os.path.getctime(path)
            ).strftime("%Y-%m-%d %H:%M:%S")
            if parts and parts[0] == "17-短剧专题" and len(parts) > 1:
                scene = parts[1]
            elif parts and parts[0] == "_场景整合工作流":
                scene = os.path.splitext(name)[0].replace("-全能版", "")
            elif parts and parts[0] == "00-★★★★★精品" and len(parts) > 2:
                scene = parts[1]
            else:
                scene = parts[0] if parts else ""
            if models_missing:
                storage_status = "模型缺失"
            elif g_only_models and e_models:
                storage_status = "混合来源"
            elif g_only_models:
                storage_status = "G盘依赖"
            elif e_models:
                storage_status = "E盘完整"
            else:
                storage_status = "未使用本地模型"
            row = {
                    "相对路径": rel,
                    "一级目录": parts[0] if parts else "",
                    "文件名": name,
                    "原文件名": clean_to_original.get(name, name),
                    "工作流名称": os.path.splitext(name)[0],
                    "完整硬盘路径": os.path.abspath(path),
                    "所在文件夹": os.path.dirname(os.path.abspath(path)),
                    "优先级": priority(rel),
                    "适用场景": scene,
                    "核心功能": workflow_features(parts, types),
                    "节点清单": " | ".join(sorted(types)),
                    "日期": date,
                    "移入时间": moved_at,
                    "模型族": family,
                    "是否旧版": "是" if legacy else "否",
                    "API节点": " | ".join(api_nodes),
                    "输入": " / ".join(input_media) or "文本",
                    "输出": " / ".join(output_media) or "未识别",
                    "默认尺寸": " / ".join(dict.fromkeys(sizes)) or "",
                    "采样步数": " / ".join(dict.fromkeys(steps)) or "",
                    "模型总大小GB": f"{model_size / (1024 ** 3):.2f}" if model_size else "",
                    "加载器模型": " | ".join(sorted(loaders)),
                    "模型来源": " | ".join(sorted(model_sources)),
                    "存储状态": storage_status,
                    "E盘模型": " | ".join(sorted(e_models)),
                    "仅G盘模型": " | ".join(sorted(g_only_models)),
                    "G盘重复模型": " | ".join(sorted(g_duplicate_models)),
                    "待迁移": "",
                    "迁移原因": "",
                    "缺模型": " | ".join(sorted(models_missing)),
                    "插件依赖": " | ".join(sorted(plugins)),
                    "节点数": len(nodes),
                    "大小KB": f"{len(raw) / 1024:.1f}",
                    "SHA256": hashlib.sha256(raw).hexdigest(),
                    "_legacy": legacy,
                    "_api": bool(api_nodes),
                    "_missing": bool(models_missing),
                }
            rows.append(row)
            for basename in loaders:
                model_usage[basename].append(row)

    hash_groups = collections.defaultdict(list)
    for row in rows:
        hash_groups[row["SHA256"]].append(row)
    duplicate_rows = []
    for group in hash_groups.values():
        group.sort(key=lambda row: duplicate_rank(row["相对路径"]))
        primary = group[0]
        for duplicate in group[1:]:
            primary_key = (
                "00-★★★★★精品"
                if primary["相对路径"].startswith("00-★★★★★精品")
                else "分类目录"
            )
            duplicate["重复保留"] = f"{primary_key}: {primary['相对路径']}"
            duplicate_rows.append(
                {
                    "重复副本": duplicate["相对路径"],
                    "保留": primary["相对路径"],
                    "SHA256": duplicate["SHA256"],
                }
            )

    for row in rows:
        if row["_legacy"]:
            parts = row["相对路径"].split(os.sep)
            if "需补模型" in parts or "_需补模型" in parts:
                status = "需补模型"
            elif "半成品" in parts or "_半成品" in parts:
                status = "半成品"
            else:
                status = "旧版"
        elif row["_api"]:
            status = "需API"
        elif row["_missing"]:
            status = "缺模型"
        else:
            status = "本地可用"
        row["状态"] = status
        row["重复保留"] = row.get("重复保留", "")
        row["评级"] = rating_for(row)
        row["推荐"] = recommendation_for(row["评级"])
        row["推荐标签"] = recommendation_tags(row, row["评级"])
        row["评级理由"] = rating_reason(row, row["评级"])
        if row["仅G盘模型"]:
            row["待迁移"] = "是" if row["是否旧版"] == "否" else ""
            row["迁移原因"] = (
                "当前工作流依赖仅存于 G 盘的模型"
                if row["是否旧版"] == "否"
                else "归档工作流依赖仅存于 G 盘的模型"
            )
        elif row["G盘重复模型"]:
            row["迁移原因"] = "E/G 存在同名模型，需校验版本和大小"
        del row["_legacy"]
        del row["_api"]
        del row["_missing"]

    migration_models = []
    hot_priorities = {"12G首选", "场景主流程", "FLUX3专题", "精品展示"}
    for basename, uses in model_usage.items():
        entries = installed.get(basename, [])
        e_entries = [
            entry for entry in entries
            if entry[0] in {"E本机", "DWPose"}
        ]
        g_entries = [
            entry for entry in entries
            if entry[0] == "G备份"
        ]
        if not g_entries or e_entries:
            continue
        source = min(g_entries, key=lambda entry: len(entry[2]))
        source_label, source_path, relative_path = source
        unique_uses = {
            row["相对路径"]: row
            for row in uses
        }
        use_rows = list(unique_uses.values())
        active_rows = [
            row for row in use_rows
            if row["是否旧版"] == "否"
        ]
        hot_rows = [
            row for row in active_rows
            if row["优先级"] in hot_priorities or row["评级"] >= 4
        ]
        if hot_rows:
            migration_priority = "高"
            reason = f"被 {len(active_rows)} 个当前工作流引用，其中 {len(hot_rows)} 个为高优先流程"
        elif active_rows:
            migration_priority = "中"
            reason = f"被 {len(active_rows)} 个当前工作流引用"
        else:
            migration_priority = "低"
            reason = "仅被归档或旧版工作流引用"
        target_path = os.path.join(E_MODELS_ROOT, relative_path)
        migration_models.append(
            {
                "fileName": os.path.basename(source_path),
                "category": relative_path.split(os.sep)[0],
                "sizeGB": round(os.path.getsize(source_path) / (1024 ** 3), 3),
                "sourceLabel": source_label,
                "sourcePath": source_path,
                "targetPath": target_path,
                "targetDirectory": os.path.dirname(target_path),
                "priority": migration_priority,
                "reason": reason,
                "workflowCount": len(use_rows),
                "activeWorkflowCount": len(active_rows),
                "hotWorkflowCount": len(hot_rows),
                "maxRating": max((row["评级"] for row in use_rows), default=0),
                "sampleWorkflows": [
                    row["工作流名称"]
                    for row in sorted(
                        use_rows,
                        key=lambda row: (
                            row["是否旧版"] == "是",
                            -row["评级"],
                            row["工作流名称"],
                        ),
                    )[:10]
                ],
            }
        )
    migration_order = {"高": 0, "中": 1, "低": 2}
    migration_models.sort(
        key=lambda item: (
            migration_order.get(item["priority"], 9),
            -item["hotWorkflowCount"],
            -item["activeWorkflowCount"],
            -item["sizeGB"],
            item["fileName"].lower(),
        )
    )
    with open(MIGRATION_PATH, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            {
                "generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "models": migration_models,
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )
        handle.write("\n")

    fieldnames = [
        "状态",
        "评级",
        "推荐",
        "优先级",
        "工作流名称",
        "适用场景",
        "核心功能",
        "推荐标签",
        "评级理由",
        "完整硬盘路径",
        "所在文件夹",
        "相对路径",
        "一级目录",
        "文件名",
        "原文件名",
        "日期",
        "移入时间",
        "模型族",
        "是否旧版",
        "API节点",
        "输入",
        "输出",
        "默认尺寸",
        "采样步数",
        "模型总大小GB",
        "加载器模型",
        "模型来源",
        "存储状态",
        "E盘模型",
        "仅G盘模型",
        "G盘重复模型",
        "待迁移",
        "迁移原因",
        "缺模型",
        "插件依赖",
        "节点清单",
        "节点数",
        "大小KB",
        "重复保留",
        "SHA256",
    ]
    priority_order = {
        "场景主流程": 0,
        "12G首选": 1,
        "FLUX3专题": 2,
        "精品展示": 3,
        "分类流程": 4,
        "归档": 5,
    }
    rows.sort(
        key=lambda row: (
            priority_order.get(row["优先级"], 9),
            -row["评级"],
            row["状态"],
            row["一级目录"],
            row["文件名"],
        )
    )
    with open(
        os.path.join(WF, "工作流总索引.csv"),
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    current = [row for row in rows if row["是否旧版"] != "是"]
    categories = sorted(
        {
            row["相对路径"].split(os.sep)[0]
            for row in current
            if row["相对路径"].split(os.sep)[0] != "_归档"
        }
    )
    archive_counts = collections.Counter(
        row["状态"] for row in rows if row["是否旧版"] == "是"
    )
    lines = [
        "# ComfyUI 分类导航",
        "",
        "生成日期：2026-10-19",
        "",
        f"- 当前流程：{len(current)} 个（含精品目录中的重复展示副本）",
        f"- 本地可用：{sum(row['状态'] == '本地可用' for row in rows)} 个",
        f"- 需 API：{sum(row['状态'] == '需API' for row in rows)} 个",
        f"- 需补模型：{sum(row['状态'] == '需补模型' for row in rows)} 个",
        f"- 归档旧版：{archive_counts['旧版']} 个",
        f"- 归档半成品：{archive_counts['半成品']} 个",
        "",
        "> 主分类只放当前流程。旧版、半成品和缺模型流程统一放在 `_归档/`。",
        "> 完整字段、场景、功能、模型来源、插件依赖和节点清单请看 `工作流总索引.csv`。",
        "",
    ]
    for category in categories:
        cat_rows = [
            row
            for row in current
            if row["相对路径"].split(os.sep)[0] == category
        ]
        local = [row for row in cat_rows if row["状态"] == "本地可用"]
        api = [row for row in cat_rows if row["状态"] == "需API"]
        missing = [row for row in cat_rows if row["状态"] == "需补模型"]
        archived = [
            row
            for row in rows
            if row["相对路径"].split(os.sep)[0] == "_归档"
            and category in row["相对路径"].split(os.sep)
        ]
        old_count = sum(row["状态"] == "旧版" for row in archived)
        half_count = sum(row["状态"] == "半成品" for row in archived)
        lines.extend(
            [
                f"## {category}",
                "",
                f"本地可用 {len(local)}｜需 API {len(api)}｜需补模型 {len(missing)}｜"
                f"归档旧版 {old_count}｜归档半成品 {half_count}",
                "",
            ]
        )
        if local or api:
            lines.extend(
                [
                    "| 状态 | 工作流 | 模型族 | 输入 → 输出 | 设置 | 模型合计 |",
                    "|---|---|---|---|---|---|",
                ]
            )
            for row in sorted(local + api, key=lambda item: item["文件名"]):
                settings = " / ".join(
                    value
                    for value in (
                        row["默认尺寸"],
                        f"{row['采样步数']} 步" if row["采样步数"] else "",
                    )
                    if value
                )
                lines.append(
                    "| {status} | {name} | {family} | {io} | {settings} | {size} |".format(
                        status=row["状态"],
                        name=row["文件名"].replace("|", "\\|"),
                        family=row["模型族"],
                        io=f"{row['输入']} → {row['输出']}",
                        settings=settings,
                        size=f"{row['模型总大小GB']} GB" if row["模型总大小GB"] else "",
                    )
                )
            lines.append("")
        notes = {
            "03-换脸人像一致性": (
                "当前没有专用本地新流。优先用 `02-图像编辑-风格迁移/"
                "Qwen-image2.1 图像编辑模式` 做身份保持、换装和换场景。"
            ),
            "04-局部重绘-扩图-消除": (
                "当前没有专用本地新流。优先用 Qwen-Image 2.1 图像编辑模式；"
                "高质量商业局部重绘可参考旧版，但需要补 FLUX.1 系列模型。"
            ),
            "12-字体海报-二维码-图标": (
                "当前没有专用本地新流。海报和详情页优先用 API 目录；"
                "文字排版要求高时使用 GPT-image 2.5 或 Qwen-Image 2.1。"
            ),
            "13-室内建筑": (
                "当前没有专用本地新流。优先用 Qwen-Image 2.1 图像编辑模式，"
                "或在 API 目录里用 GPT-image 系列。"
            ),
        }
        if category in notes:
            lines.extend([f"当前替代方案：{notes[category]}", ""])

    with open(
        os.path.join(WF, "分类导航.md"),
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        handle.write("\n".join(lines))

    stats = collections.Counter(row["状态"] for row in rows)
    print(f"workflows={len(rows)} unique={len(hash_groups)} duplicates={len(duplicate_rows)}")
    print("status=" + json.dumps(stats, ensure_ascii=False))
    print(f"index_csv={os.path.join(WF, '工作流总索引.csv')}")
    print(f"migration_json={MIGRATION_PATH} models={len(migration_models)}")
    print(f"navigation={os.path.join(WF, '分类导航.md')}")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Build a self-contained HTML browser from the workflow index CSV."""

import csv
import datetime
import json
import os
import re
import shutil
from collections import defaultdict


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
CSV_PATH = os.path.join(WF, "工作流总索引.csv")
OUT_PATH = os.path.join(WF, "工作流总索引.html")
LOCALDOCK_OUT_PATH = os.path.join(WF, "workflow-index.html")
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "workflow_index_template.html")
SCENE_GUIDE_PATH = os.path.join(WF, "模型场景建议与G盘迁移清单.md")
MEDIA_MANIFEST_PATH = os.path.join(WF, "_媒体预览缓存", "manifest.json")
MIGRATION_PATH = os.path.join(WF, "模型迁移清单.json")
CUSTOM_NODE_INDEX_PATH = env_path(
    "PLUGIN_INDEX_PATH",
    os.path.join(
        COMFYUI_ROOT,
        "custom_nodes",
        "comfyui_workflow_index_bridge",
        "web",
        "index.html",
    ),
)

FIELD_MAP = {
    "状态": "status",
    "评级": "rating",
    "推荐": "recommendation",
    "优先级": "priority",
    "工作流名称": "name",
    "适用场景": "scene",
    "核心功能": "features",
    "推荐标签": "recommendationTags",
    "评级理由": "ratingReason",
    "完整硬盘路径": "path",
    "所在文件夹": "folder",
    "相对路径": "relative",
    "一级目录": "category",
    "文件名": "filename",
    "原文件名": "originalName",
    "日期": "date",
    "移入时间": "movedAt",
    "模型族": "family",
    "是否旧版": "legacy",
    "API节点": "apiNodes",
    "输入": "input",
    "输出": "output",
    "默认尺寸": "size",
    "采样步数": "steps",
    "模型总大小GB": "modelGB",
    "加载器模型": "models",
    "模型来源": "modelSource",
    "存储状态": "storageStatus",
    "E盘模型": "eModels",
    "仅G盘模型": "gOnlyModels",
    "G盘重复模型": "gDuplicateModels",
    "待迁移": "needsMigration",
    "迁移原因": "migrationReason",
    "缺模型": "missing",
    "插件依赖": "plugins",
    "节点清单": "nodes",
    "节点数": "nodeCount",
    "大小KB": "fileKB",
    "重复保留": "duplicateOf",
    "SHA256": "sha",
}

SCENE_DESCRIPTIONS = {
    "01-分镜与剧本": (
        "适合小说改剧本、剧情拆解、自动分镜和镜头提示词生成，"
        "可作为从文字到短剧镜头表的入口流程。"
    ),
    "02-角色与场景": (
        "适合短剧角色设定、多角度资产、场景概念和一致性编辑，"
        "用于建立跨镜头复用的角色与环境基准。"
    ),
    "03-视频生成": (
        "适合把短剧分镜转成视频，包含本地 H3、参考图、首尾帧或云 API 视频链路，"
        "可按硬件和账号条件选择执行方式。"
    ),
    "04-动作迁移": (
        "适合把参考视频中的动作和表情迁移到角色图片，"
        "用于短剧动作镜头、舞蹈和角色表演测试。"
    ),
    "00-12G首选": (
        "面向 12GB 显存整理的日常主力方案，兼顾生成质量、速度和稳定性；"
        "适合快速出图、效果验证以及继续衔接放大、修复或局部编辑。"
    ),
    "01-摄影后期修图": (
        "适合人像、写真、商业摄影与日常选片后期，可完成肤质优化、光影统一、"
        "背景清理、瑕疵修复和细节放大，覆盖从原片调整到成片输出的主要环节。"
    ),
    "01-文生图": (
        "适合把中文或英文创意描述快速转成摄影画面、插画、海报概念和商品场景；"
        "可通过提示词增强、风格控制、LoRA 与放大模块继续细化结果。"
    ),
    "02-老照片修复": (
        "适合扫描旧照、模糊人像、破损家庭照片和低清纪念影像，重点处理噪点、"
        "划痕、褪色、模糊与脸部细节，同时尽量保留人物原貌和年代质感。"
    ),
    "02-图像编辑-风格迁移": (
        "适合在保留主体结构的前提下做局部重绘、对象移除、风格转换、材质替换"
        "和画面统一，常用于照片改风格、动漫转真人及参考图再创作。"
    ),
    "02-图像编辑与重绘": (
        "适合已有图片的精修与再创作，包括局部修改、人物一致性、换装、抠图、"
        "模糊修复和多视图生成，可直接服务商业修图与角色设定。"
    ),
    "03-文生图": (
        "适合从文字快速生成高质量主视觉、写实摄影、插画和风格化画面；"
        "强调提示词理解、构图控制与后续放大，适合高频创意出图。"
    ),
    "03-放大超分": (
        "适合低分辨率图片或视频的清晰度提升，可恢复纹理、边缘和细节，"
        "用于旧素材翻新、成片精修、打印尺寸扩展和交付前画质增强。"
    ),
    "04-视频生成": (
        "适合文生视频、图生视频、首尾帧过渡、多参考视频、分镜剧情和镜头扩展；"
        "可结合提示词增强、LoRA、镜头控制与视频合成完成短片段创作。"
    ),
    "04-图生图": (
        "适合以原图为基础重绘构图、光线、材质和风格，同时保留人物、产品或场景"
        "主体特征，常用于概念迭代、效果改版和成片精修。"
    ),
    "05-放大超分-修复": (
        "适合模糊照片、压缩素材和低清图片的修复放大，重点改善轮廓、纹理、"
        "噪点和细节，让旧图或小图达到更可用的交付尺寸。"
    ),
    "05-风格迁移": (
        "适合照片转插画、胶片与电影感调色、产品质感迁移和艺术化重绘；"
        "在保留主体构图的同时统一色彩、材质、笔触与整体视觉语言。"
    ),
    "05-音频语音": (
        "适合角色配音、声音克隆、口播旁白和音频内容试制，可基于参考声音生成"
        "稳定的本地语音，并继续用于视频、动画或播客流程。"
    ),
    "06-电商与内容": (
        "适合商品主图、详情页、营销海报、模特展示和多语言内容制作；"
        "可串联产品图生成、场景合成、文字排版、放大和视频化输出。"
    ),
    "06-抠图换背景-合成": (
        "适合人物、商品和复杂主体的精确提取，可衔接纯色底、棚拍背景、"
        "生活场景或营销合成，用于电商图和内容平台素材制作。"
    ),
    "06-视频生成": (
        "适合短视频、动态海报、角色动作和分镜演示，支持文本或图片驱动，"
        "可继续做补帧、超分、转绘与成片合成。"
    ),
    "07-电商产品": (
        "适合产品主图、场景种草图、详情页模块和广告画面生成，可围绕商品外观、"
        "材质、卖点和投放尺寸组织视觉内容，并衔接文案与视频输出。"
    ),
    "07-工具与LLM": (
        "适合提示词反推、多轮对话、文本策划、语义分割和工具节点编排，"
        "用于补足生成流程中的理解、分析与自动化能力。"
    ),
    "07-音乐生成": (
        "适合短视频配乐、氛围音乐、片头片尾和创意声音实验，可依据文字描述"
        "生成音乐片段并继续进入视频合成流程。"
    ),
    "08-字体海报": (
        "适合活动海报、品牌主视觉、社媒封面和字体排版试验，可将文字创意、"
        "画面生成、版式控制与高清输出组织在同一套流程中。"
    ),
    "08-换装模特": (
        "适合服装试穿、模特换装、商品穿搭和人物一致性展示，可保留人物特征与"
        "服装细节，用于电商上新、提案和社交媒体内容。"
    ),
    "09-电商产品": (
        "适合商品展示、卖点场景、详情页和广告素材制作，可生成不同材质、"
        "灯光与使用场景，并衔接放大和营销内容输出。"
    ),
    "09-摄影写真-头像证件照": (
        "适合写真、社交媒体头像、个人形象照和基础证件照生成，可控制人物风格、"
        "背景、服装与构图，并进行清晰度和细节增强。"
    ),
    "10-抠图换背景": (
        "适合人像、商品和复杂物体抠图，可生成精细遮罩并替换为白底、棚拍、"
        "自然场景或广告背景，便于继续合成和排版。"
    ),
    "10-视频生成": (
        "适合连续镜头、剧情分镜、参考驱动视频和短视频片段创作，可组合剧本、"
        "关键帧、提示词、运镜和音频，形成较完整的视频制作链路。"
    ),
    "11-换脸人像": (
        "适合人物换脸、面部一致性、角色替换和人像合成，重点保持五官、肤色、"
        "光影与头部姿态自然，可用于写真、短剧和角色内容。"
    ),
    "11-视频后期-转绘超分插帧": (
        "适合已有视频的画质增强与风格化处理，包括超分、补帧、转绘和镜头稳定，"
        "可用于旧视频翻新、动画化和交付前质量提升。"
    ),
    "12-多视图角色": (
        "适合角色设定、三视图/四视图、表情与服装一致性展示，可生成多角度参考，"
        "用于动画、游戏、漫画和后续建模资料。"
    ),
    "13-图片超分修复": (
        "适合低清图片、压缩图片和细节损坏素材，通过修复与放大改善纹理、边缘、"
        "人脸和产品细节，适合打印、上架和二次编辑。"
    ),
    "14-音频语音音乐": (
        "适合声音克隆、角色配音、旁白、音乐片段和音频实验，可与其他流程组合，"
        "为视频、动画、播客和展示内容提供声音素材。"
    ),
    "15-3D多视图-手办": (
        "适合角色三视图、手办概念、白模参考和多角度设定，可保持造型与服装一致，"
        "为3D建模、打印和周边设计提供参考资料。"
    ),
    "16-工具-LLM辅助": (
        "适合提示词反推、图像理解、多轮对话、抠图和自动化辅助，可嵌入其他工作流，"
        "减少手工整理并提高生成流程的可控性。"
    ),
    "FLUX3工作流": (
        "适合体验 FLUX.3 Klein 的文生图与图像编辑能力，覆盖官方、蒸馏和 12GB 兼容"
        "路线，可用于新模型效果验证、风格探索和后续场景流程替换。"
    ),
}

ARCHIVE_SCENE_RULES = [
    (("磨皮", "精修", "肤质", "皮肤"), "人像美肤、商业修图和肤质细节优化"),
    (("换装", "换衣", "试穿", "穿搭", "模特"), "人物换装、服装试穿和模特展示"),
    (("换背景", "背景", "白底", "场景替换"), "主体换背景、白底图与场景合成"),
    (("产品", "商品", "电商", "详情页", "海报"), "商品展示、详情页和营销视觉制作"),
    (("多角度", "多视图", "四视图", "三视图", "角色"), "角色设定、多视图和一致性参考"),
    (("3D", "手办", "白模", "建模"), "角色转3D、手办概念和建模参考"),
    (("放大", "超分", "高清"), "低清图像/视频放大和细节增强"),
    (("修复", "模糊", "老照片", "破损"), "模糊图像、旧照和细节损坏修复"),
    (("线稿", "轮廓", "深度", "pose", "姿态", "ControlNet"), "线稿、深度、姿态和结构控制"),
    (("溶图", "融合", "质感", "风格", "滤镜", "调色", "迁移"), "质感迁移、风格融合和画面统一"),
    (("视频", "动画", "分镜", "运镜", "漫剧"), "视频生成、分镜和动态内容制作"),
    (("抠图", "遮罩", "分割", "去背景", "matting", "mask"), "主体提取、语义分割和精细遮罩"),
    (("LLM", "提示词", "对话", "GPT", "剧本"), "提示词生成、文本策划和LLM辅助"),
    (("音频", "声音", "语音", "音乐", "TTS", "配音"), "声音克隆、配音和音乐生成"),
]

FEATURE_LABELS = {
    "生成/采样": "生成采样",
    "Qwen指令编辑": "Qwen指令编辑",
    "高清放大": "高清放大",
    "LLM提示词": "提示词增强",
    "MiniMax视频/音频": "MiniMax视频/音频",
    "视频合成": "视频合成",
    "ControlNet": "ControlNet结构控制",
}


def summarize_features(value, limit=4):
    features = []
    for item in str(value or "").split("|"):
        item = item.strip()
        if item:
            features.append(FEATURE_LABELS.get(item, item))
    return "、".join(features[:limit])


def scene_description(row):
    scene = row["scene"]
    if scene == "_归档":
        searchable = " ".join(
            [row["name"], row["originalName"], row["features"], row["category"]]
        )
        intent = "历史实验、参数调试和可复用节点参考"
        for keywords, description in ARCHIVE_SCENE_RULES:
            if any(keyword.lower() in searchable.lower() for keyword in keywords):
                intent = description
                break
        family = row["family"] or "通用"
        features = summarize_features(row["features"], 3)
        detail = (
            f"归档参考，适合{intent}。该样本基于{family}流程"
            f"{('，保留' + features + '等能力') if features else ''}，"
            "可用于查找旧节点、参数和效果对照，不建议直接作为当前首选。"
        )
        return detail

    parts = []
    base = SCENE_DESCRIPTIONS.get(scene)
    if base:
        parts.append(base.rstrip("。"))
    else:
        parts.append(f"适合{scene.replace('-', '、')}相关任务")

    family = row["family"].strip()
    if family:
        parts.append(f"当前流程基于{family}")
    features = summarize_features(row["features"])
    if features:
        parts.append(f"重点包含{features}")
    input_type = row["input"].strip()
    output_type = row["output"].strip()
    if input_type and output_type:
        parts.append(f"通常接收{input_type}并输出{output_type}")
    if row["status"] == "需API":
        parts.append("部分环节依赖云端API")
    elif row["priority"] == "12G首选":
        parts.append("已按12GB显存路线整理")
    return "；".join(part for part in parts if part) + "。"


def markdown_section(text, title):
    marker = f"## {title}"
    start = text.find(marker)
    if start < 0:
        return []
    start += len(marker)
    end = text.find("\n## ", start)
    return text[start : end if end >= 0 else None].splitlines()


def markdown_table(lines):
    table_lines = [line.strip() for line in lines if line.strip().startswith("|")]
    if len(table_lines) < 3:
        return {"headers": [], "rows": []}

    def cells(line):
        return [cell.strip() for cell in line.strip("|").split("|")]

    return {
        "headers": cells(table_lines[0]),
        "rows": [cells(line) for line in table_lines[2:]],
    }


def load_scene_guides():
    if not os.path.exists(SCENE_GUIDE_PATH):
        return {
            "updatedAt": "",
            "rankings": [],
            "sceneModels": {"headers": [], "rows": []},
            "coverage": [],
        }
    with open(SCENE_GUIDE_PATH, "r", encoding="utf-8") as handle:
        text = handle.read()

    rankings = []
    current = None
    for line in markdown_section(text, "当前综合排行"):
        stripped = line.strip()
        if stripped.startswith("### "):
            current = {"title": stripped[4:].strip(), "items": []}
            rankings.append(current)
        elif current and re.match(r"^\d+\.\s+", stripped):
            current["items"].append(re.sub(r"^\d+\.\s+", "", stripped))

    scene_models = markdown_table(markdown_section(text, "各场景推荐模型"))
    coverage_table = markdown_table(markdown_section(text, "场景工作流覆盖"))
    coverage = []
    for row in coverage_table["rows"]:
        if len(row) < 3:
            continue
        coverage.append(
            {
                "scene": row[0],
                "representative": row[1],
                "conclusion": row[2],
                "workflowNames": re.findall(r"`([^`]+)`", row[1]),
            }
        )

    updated_match = re.search(r"更新日期：([^\n]+)", text)
    return {
        "updatedAt": updated_match.group(1).strip() if updated_match else "",
        "rankings": rankings,
        "sceneModels": scene_models,
        "coverage": coverage,
    }


def main():
    rows = []
    with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            rows.append({FIELD_MAP[key]: raw.get(key, "") for key in FIELD_MAP})
    media_by_workflow = defaultdict(list)
    if os.path.exists(MEDIA_MANIFEST_PATH):
        with open(MEDIA_MANIFEST_PATH, "r", encoding="utf-8") as handle:
            media_items = json.load(handle)
        for item in media_items:
            relative = str(item.get("workflowRelative") or "").replace("\\", "/")
            if not relative:
                continue
            media_by_workflow[relative].append(
                {
                    "name": item.get("name", ""),
                    "relative": item.get("relative", ""),
                    "kind": item.get("kind", ""),
                    "url": item.get("url", ""),
                    "thumb": item.get("thumb", ""),
                    "size": item.get("size", 0),
                    "modified": item.get("modified", ""),
                    "dimensions": item.get("dimensions", ""),
                    "duration": item.get("duration"),
                    "hasWorkflowMetadata": item.get("hasWorkflowMetadata", False),
                    "workflowMatch": item.get("workflowMatch", ""),
                }
            )
    for row in rows:
        row["sceneDetail"] = scene_description(row)
        relative = row["relative"].replace("\\", "/")
        media = media_by_workflow.get(relative, [])
        row["media"] = sorted(
            media, key=lambda item: item.get("modified", ""), reverse=True
        )
        row["mediaCount"] = str(len(row["media"]))
    model_migrations = {"generatedAt": "", "models": []}
    if os.path.exists(MIGRATION_PATH):
        with open(MIGRATION_PATH, "r", encoding="utf-8") as handle:
            model_migrations = json.load(handle)
    data = {
        "generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sceneGuides": load_scene_guides(),
        "modelMigrations": model_migrations,
        "rows": rows,
    }
    template = open(TEMPLATE_PATH, "r", encoding="utf-8").read()
    payload = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    html = template.replace("__WORKFLOW_DATA__", payload).replace(
        "__GENERATED_AT__",
        data["generatedAt"],
    )
    output_paths = [OUT_PATH, LOCALDOCK_OUT_PATH, CUSTOM_NODE_INDEX_PATH]

    for output_path in dict.fromkeys(output_paths):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(html)
        print(f"html={output_path}")

    plugin_web = os.path.dirname(CUSTOM_NODE_INDEX_PATH)
    thumbnail_source = os.path.join(WF, "_媒体预览缓存", "thumbnails")
    thumbnail_target = os.path.join(
        plugin_web, "_媒体预览缓存", "thumbnails"
    )
    if os.path.isdir(thumbnail_source):
        shutil.copytree(thumbnail_source, thumbnail_target, dirs_exist_ok=True)
        print(f"thumbnails={thumbnail_target}")

    print(f"rows={len(rows)} bytes={os.path.getsize(OUT_PATH)}")


if __name__ == "__main__":
    main()

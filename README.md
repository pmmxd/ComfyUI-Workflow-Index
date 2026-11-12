# ComfyUI 工作流总索引

[English](#english)

一个面向本地 ComfyUI 的工作流整理、检索和媒体预览工具。它扫描 ComfyUI 工作流目录，读取工作流节点、模型引用、插件依赖、文件时间和生成媒体，输出可筛选的静态 HTML 索引，并可在 ComfyUI 左侧栏中直接打开。

本项目只发布源代码，不包含任何模型、工作流、图片、视频、数据库或用户生成内容。

## 主要功能

- 自动扫描 ComfyUI 工作流 JSON，生成 CSV、Markdown 分类导航和静态 HTML。
- 按场景、评级、推荐标签、状态、模型、插件、移入时间和生成媒体筛选。
- 显示工作流绝对路径，支持复制路径和在 ComfyUI 中打开。
- 扫描 ComfyUI 输出目录，关联工作流与图片、视频、音频预览。
- 可选安装 ComfyUI 侧栏桥接插件，在 ComfyUI 页面内打开索引。
- 生成的 `workflow-index.html` 可直接交给 LocalDock 作为本地静态站点入口。

## 不包含的数据

公开仓库不会包含以下内容：

- 工作流 JSON、生成的 CSV/HTML 索引。
- 模型、LoRA、ControlNet、文本编码器或其他权重文件。
- `ComfyUI/output`、预览缩略图、图片、视频和音频。
- SQLite 数据库、日志、凭据、Cookie、令牌和个人配置。
- 个人整理的场景建议、模型迁移清单或收藏数据。

索引页面会显示运行机器上的绝对路径和模型文件名，因此它适合本机使用。提交到 Git 或对外分享前，请检查并删除所有生成结果。

## 环境要求

- Windows 10/11。
- 已安装并至少启动过一次 ComfyUI。
- Python 3.10 或更高版本。
- FFmpeg 可选。安装 `ffprobe` 后可读取视频时长和嵌入元数据。
- [LocalDock](https://github.com/pmmxd/localdock) 可选，但推荐用于启动和管理静态索引页面。

## 安装

```powershell
git clone https://github.com/pmmxd/ComfyUI-Workflow-Index.git
Set-Location ComfyUI-Workflow-Index
python -m pip install -r requirements.txt
```

将侧栏插件复制到 ComfyUI：

```powershell
$env:COMFYUI_ROOT = "D:\ComfyUI"
Copy-Item .\comfyui_workflow_index_bridge `
  (Join-Path $env:COMFYUI_ROOT "custom_nodes\comfyui_workflow_index_bridge") `
  -Recurse
```

如果 ComfyUI 已经存在同名插件目录，请先比较并备份原目录，不要直接覆盖。

## 配置

至少需要设置 `COMFYUI_ROOT`。路径应指向包含 `models`、`custom_nodes`、`output` 和 `user` 的 ComfyUI 根目录。

```powershell
$env:COMFYUI_ROOT = "D:\ComfyUI"
```

可选环境变量：

| 变量 | 用途 |
|---|---|
| `COMFYUI_WORKFLOWS_DIR` | 覆盖默认工作流目录 `COMFYUI_ROOT\user\default\workflows` |
| `COMFYUI_MODELS_DIR` | 覆盖默认模型目录 `COMFYUI_ROOT\models` |
| `EXTRA_MODEL_DIRS` | 额外模型目录，多个路径用 Windows 分号 `;` 分隔 |
| `CONTROLNET_AUX_ROOT` | 覆盖 ControlNet Aux 的 `ckpts` 目录 |
| `FFPROBE_PATH` | 指定 `ffprobe.exe`，未设置时从 `PATH` 查找 `ffprobe` |
| `PLUGIN_INDEX_PATH` | 覆盖侧栏插件 `web\index.html` 的输出位置 |
| `COMFYUI_PYTHON` | 指定运行脚本的 Python 可执行文件 |

示例：

```powershell
$env:COMFYUI_ROOT = "D:\ComfyUI"
$env:EXTRA_MODEL_DIRS = "E:\model-backup;F:\shared-models"
$env:FFPROBE_PATH = "C:\ffmpeg\bin\ffprobe.exe"
```

## 运行

在工作流目录中放入 JSON 工作流后，执行：

```powershell
.\update-workflow-data.ps1
```

脚本按固定顺序运行：

1. `rebuild_workflow_index.py`：扫描工作流、模型和插件，生成 CSV 与分类导航。
2. `generate_media_preview.py`：扫描输出媒体，生成缩略图和预览清单。
3. `build_workflow_html.py`：生成中文索引、LocalDock 入口和 ComfyUI 侧栏页面。

也可以手动逐条执行：

```powershell
python -X utf8 .\tools\rebuild_workflow_index.py
python -X utf8 .\tools\generate_media_preview.py
python -X utf8 .\tools\build_workflow_html.py
```

主要输出：

```text
COMFYUI_ROOT\user\default\workflows\工作流总索引.csv
COMFYUI_ROOT\user\default\workflows\工作流总索引.html
COMFYUI_ROOT\user\default\workflows\workflow-index.html
COMFYUI_ROOT\user\default\workflows\媒体预览测试.html
COMFYUI_ROOT\custom_nodes\comfyui_workflow_index_bridge\web\index.html
```

## 使用 LocalDock 运行

1. 从 [LocalDock Releases](https://github.com/pmmxd/localdock/releases/latest) 下载并解压 Windows 便携版。
2. 运行 `LocalDock.exe`。
3. 新建一个静态站点。
4. 将站点目录设为 `COMFYUI_ROOT\user\default\workflows`。
5. 使用自动分配端口，或手动指定一个未占用端口，例如 `8898`。
6. 启动站点并打开 `http://127.0.0.1:8898/workflow-index.html`。

LocalDock 管理的是静态网页服务，不会自动重新扫描工作流。添加或删除工作流后，需要重新运行 `update-workflow-data.ps1`。

## 在 ComfyUI 中使用

1. 确认桥接插件已放在 `COMFYUI_ROOT\custom_nodes\comfyui_workflow_index_bridge`。
2. 重启 ComfyUI。
3. 打开 `http://127.0.0.1:8188/`。
4. 在左侧栏打开“工作流索引”。

如果浏览器仍显示旧数据，按 `Ctrl+F5` 强制刷新。HTML 页面中的 ComfyUI 地址可以在页面顶部修改并保存在当前浏览器中。

## 可选输入

以下文件由用户自行提供，不存在时生成器仍可运行：

- `模型场景建议与G盘迁移清单.md`：提供综合排行、场景模型建议和代表工作流。
- `模型迁移清单.json`：由索引脚本自动生成，用于展示模型迁移建议。
- `_个人精品.json`：侧栏插件使用的本地收藏数据，不应提交到公开仓库。

## 常见问题

### 提示找不到 `COMFYUI_ROOT`

当前 PowerShell 会话没有设置环境变量。重新执行：

```powershell
$env:COMFYUI_ROOT = "D:\ComfyUI"
```

### 视频没有时长或缩略图

检查 `FFPROBE_PATH`，并确认 OpenCV 可以读取该视频编码。必要时安装 FFmpeg 后重新运行。

### LocalDock 打不开页面

确认站点目录指向 `COMFYUI_ROOT\user\default\workflows`，并确认该目录下已经生成 `workflow-index.html`。

### ComfyUI 左侧没有“工作流索引”

确认插件目录层级为 `custom_nodes\comfyui_workflow_index_bridge\__init__.py`，然后重启 ComfyUI 并查看启动日志。

## 隐私说明

本项目在本地运行，不会主动上传 ComfyUI 数据。它生成的索引可能包含本机绝对路径、工作流名称、模型名称和媒体文件信息。不要把这些生成结果提交到公开仓库，也不要在没有清理数据的情况下部署到公网。

---

## English

A local-first workflow catalog, search interface, and media preview tool for ComfyUI. It scans workflow JSON files, node types, model references, custom-node dependencies, file timestamps, and generated output media, then builds filterable static HTML pages that can also open inside the ComfyUI sidebar.

This repository contains source code only. Models, workflows, images, videos, databases, and user-generated media are not included.

### Features

- Scans ComfyUI workflow JSON and builds CSV, Markdown navigation, and static HTML.
- Filters by scene, rating, recommendation tags, status, model family, plugins, import time, and generated media.
- Copies absolute workflow paths and opens workflows in ComfyUI.
- Associates generated images, videos, and audio with their workflows.
- Includes an optional ComfyUI sidebar bridge.
- Produces `workflow-index.html` for use with LocalDock.

### Requirements

- Windows 10/11.
- A working ComfyUI installation.
- Python 3.10 or newer.
- Optional: FFmpeg/`ffprobe` for video duration and metadata.
- Optional but recommended: [LocalDock](https://github.com/pmmxd/localdock).

### Quick Start

```powershell
git clone https://github.com/pmmxd/ComfyUI-Workflow-Index.git
Set-Location ComfyUI-Workflow-Index
python -m pip install -r requirements.txt
$env:COMFYUI_ROOT = "D:\ComfyUI"
```

Copy `comfyui_workflow_index_bridge` into:

```text
COMFYUI_ROOT\custom_nodes\comfyui_workflow_index_bridge
```

Then run:

```powershell
.\update-workflow-data.ps1
```

The script runs, in order:

```text
tools\rebuild_workflow_index.py
tools\generate_media_preview.py
tools\build_workflow_html.py
```

Generated files include:

```text
COMFYUI_ROOT\user\default\workflows\工作流总索引.csv
COMFYUI_ROOT\user\default\workflows\工作流总索引.html
COMFYUI_ROOT\user\default\workflows\workflow-index.html
COMFYUI_ROOT\user\default\workflows\媒体预览测试.html
COMFYUI_ROOT\custom_nodes\comfyui_workflow_index_bridge\web\index.html
```

### LocalDock Setup

1. Download the portable Windows build from [LocalDock Releases](https://github.com/pmmxd/localdock/releases/latest).
2. Run `LocalDock.exe`.
3. Create a static site and set its directory to `COMFYUI_ROOT\user\default\workflows`.
4. Start the site.
5. Open `http://127.0.0.1:8898/workflow-index.html`, or use the port assigned by LocalDock.

LocalDock serves the generated page. Re-run `update-workflow-data.ps1` whenever workflows or output media change.

### ComfyUI Sidebar

After installing the bridge plugin and restarting ComfyUI, open `http://127.0.0.1:8188/` and select **Workflow Index** in the left sidebar. Press `Ctrl+F5` if the browser shows stale content.

### Optional Configuration

| Variable | Purpose |
|---|---|
| `COMFYUI_WORKFLOWS_DIR` | Override the default workflow directory |
| `COMFYUI_MODELS_DIR` | Override the default model directory |
| `EXTRA_MODEL_DIRS` | Additional model roots separated by `;` |
| `CONTROLNET_AUX_ROOT` | Override the ControlNet Aux `ckpts` directory |
| `FFPROBE_PATH` | Path to `ffprobe.exe` |
| `PLUGIN_INDEX_PATH` | Override the generated sidebar index path |
| `COMFYUI_PYTHON` | Python executable used by the update script |

### Privacy

All processing happens locally. Generated indexes may contain local absolute paths, workflow names, model names, and media metadata. Review and sanitize generated files before committing or publishing them.

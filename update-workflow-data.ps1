param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

if (-not $env:COMFYUI_ROOT) {
    throw "请先设置 COMFYUI_ROOT，指向 ComfyUI 根目录。"
}

if (-not $Python) {
    $Python = if ($env:COMFYUI_PYTHON) { $env:COMFYUI_PYTHON } else { "python" }
}

$Workflows = if ($env:COMFYUI_WORKFLOWS_DIR) {
    $env:COMFYUI_WORKFLOWS_DIR
} else {
    Join-Path $env:COMFYUI_ROOT "user\default\workflows"
}

if (-not (Test-Path -LiteralPath $Workflows -PathType Container)) {
    throw "找不到 ComfyUI 工作流目录：$Workflows"
}

$Tools = Join-Path $PSScriptRoot "tools"
$Steps = @(
    "rebuild_workflow_index.py",
    "generate_media_preview.py",
    "build_workflow_html.py"
)

foreach ($Step in $Steps) {
    Write-Host ""
    Write-Host "==> $Step"
    & $Python -X utf8 (Join-Path $Tools $Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step 执行失败，退出代码：$LASTEXITCODE"
    }
}

Write-Host ""
Write-Host "索引已更新："
Write-Host (Join-Path $Workflows "workflow-index.html")
Write-Host "ComfyUI 侧栏入口：http://127.0.0.1:8188/"

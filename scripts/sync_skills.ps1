# sync_skills.ps1 - 把工作区 skill 同步到用户根，使其它 cwd 的会话也能用。
#
# 为什么需要：DSH 的 skill 根按 rank 扫描——
#   <projectRoot>/.agents/skills  (200)  <- 本仓库，免提权、热加载，但只在 projectRoot=cwd 时生效
#   <agentsHome>/skills          (500)  <- 用户根，全局可见，但需要写权限
#
# 工作区副本是唯一真源。本脚本只做单向发布，绝不反向覆盖。
#
# 用法：
#   .\scripts\sync_skills.ps1              # 预演（默认）
#   .\scripts\sync_skills.ps1 -Execute     # 真正写入用户根
#   .\scripts\sync_skills.ps1 -Execute -Only ducted-fan-aero-design

[CmdletBinding()]
param(
    [switch]$Execute,
    [string[]]$Only,
    [string]$AgentsHome = (Join-Path $env:USERPROFILE ".agents")
)

$ErrorActionPreference = "Stop"
$repoRoot  = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $repoRoot ".agents\skills"
$targetRoot = Join-Path $AgentsHome "skills"

if (-not (Test-Path $sourceRoot)) {
    Write-Error "找不到工作区 skill 根：$sourceRoot"
    exit 3
}

$skills = Get-ChildItem -Path $sourceRoot -Directory |
    Where-Object { Test-Path (Join-Path $_.FullName "SKILL.md") }

if ($Only) {
    $skills = $skills | Where-Object { $Only -contains $_.Name }
}

if (-not $skills) {
    Write-Host "没有匹配的 skill。"
    exit 0
}

Write-Host ("工作区 skill 根 : " + $sourceRoot)
Write-Host ("用户根目标      : " + $targetRoot)
Write-Host ("模式            : " + $(if ($Execute) { "执行" } else { "预演（加 -Execute 才写入）" }))
Write-Host ""

foreach ($s in $skills) {
    $dest = Join-Path $targetRoot $s.Name
    $files = Get-ChildItem -Path $s.FullName -Recurse -File
    $bytes = ($files | Measure-Object Length -Sum).Sum
    Write-Host ("  {0,-38} {1,3} 文件  {2,8:N1} KB  ->  {3}" -f $s.Name, $files.Count, ($bytes / 1KB), $dest)
    if ($Execute) {
        if (Test-Path $dest) {
            Write-Host ("      （已存在，覆盖前先备份为 .bak-" + (Get-Date -Format "yyyyMMddHHmmss") + "）")
            $backup = $dest + ".bak-" + (Get-Date -Format "yyyyMMddHHmmss")
            Move-Item -Path $dest -Destination $backup
        }
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        Copy-Item -Path (Join-Path $s.FullName "*") -Destination $dest -Recurse -Force
        Write-Host "      已写入"
    }
}

Write-Host ""
if ($Execute) {
    Write-Host "完成。新开会话即可在任意 cwd 看到这些 skill（skill 根有 watcher，通常无需重启）。"
} else {
    Write-Host "预演结束。确认无误后加 -Execute。"
    Write-Host "提示：写用户根可能需要一次沙箱提权。"
}

# 本地AI 临时目录清理脚本
# 只清理 %TEMP% 下的 _MEI* （PyInstaller 解压残留），被占用的自动跳过，绝不强删。
# 用法：
#   powershell -ExecutionPolicy Bypass -File "清理临时文件.ps1"
#   powershell -ExecutionPolicy Bypass -File "清理临时文件.ps1" -DryRun      # 只看不删
#   定时：任务计划程序 → 创建基本任务 → 每天 → 操作选“启动程序”
#         程序：powershell.exe
#         参数：-ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\本地AI在线部署版\工具\清理临时文件.ps1"
param(
    [switch]$DryRun,
    [int]$MinAgeHours = 1
)
$ErrorActionPreference = 'SilentlyContinue'
$temp = [IO.Path]::GetTempPath()
$log = Join-Path $temp '本地AI_临时目录清理日志.txt'

function Write-Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Host $line
    Add-Content -LiteralPath $log -Value $line -Encoding UTF8
}

Write-Log "开始清理：$temp（最小保留时长 ${MinAgeHours} 小时）"

# 找出被进程占用的 _MEI 目录（有进程加载了里面的 DLL 就不删）
$usedDirs = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
Get-Process | ForEach-Object {
    $p = $_
    try {
        foreach ($m in $p.Modules) {
            if ($m.FileName -match '\\_MEI([0-9A-Za-z]+)\\') {
                $dir = Split-Path $m.FileName -Parent
                [void]$usedDirs.Add($dir)
            }
        }
    } catch {}
}

$removed = 0
$skipped = 0
$freed = 0
Get-ChildItem -LiteralPath $temp -Filter '_MEI*' -Directory -Force | ForEach-Object {
    $dir = $_
    $full = $dir.FullName
    $ageHours = ((Get-Date) - $dir.LastWriteTime).TotalHours
    if ($ageHours -lt $MinAgeHours) {
        Write-Log "跳过（太新，${ageHours:N1}h）：$($dir.Name)"
        $skipped++
        return
    }
    if ($usedDirs.Contains($full)) {
        Write-Log "跳过（被进程占用）：$($dir.Name)"
        $skipped++
        return
    }
    $size = (Get-ChildItem -LiteralPath $full -Recurse -Force | Measure-Object Length -Sum).Sum
    if ($DryRun) {
        Write-Log "将删除（试运行）：$($dir.Name)  $([math]::Round($size/1MB,1)) MB"
        $skipped++
        return
    }
    Remove-Item -LiteralPath $full -Recurse -Force
    if (-not (Test-Path -LiteralPath $full)) {
        $removed++
        $freed += $size
        Write-Log "已删除：$($dir.Name)  $([math]::Round($size/1MB,1)) MB"
    } else {
        Write-Log "删除失败（可能刚被占用）：$($dir.Name)"
        $skipped++
    }
}
Write-Log ("完成：删除 {0} 个，跳过 {1} 个，释放 {2:N1} MB" -f $removed, $skipped, ($freed/1MB))

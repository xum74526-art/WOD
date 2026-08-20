param(
  [Parameter(Mandatory=$true)][string]$ApiUrl,
  [Parameter(Mandatory=$true)][string]$Token
)
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw '请使用管理员 PowerShell 运行安装命令。'
}
$arch = if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture -eq 'Arm64') { 'arm64' } else { 'amd64' }
$root = Join-Path $env:ProgramFiles 'KAI Agent'
$data = Join-Path $env:ProgramData 'KAI\Agent'
New-Item -ItemType Directory -Force -Path $root, $data | Out-Null
& icacls.exe $data /inheritance:r /grant:r 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' | Out-Null
$binary = Join-Path $root 'kai-agent.exe'
Invoke-WebRequest "$($ApiUrl.TrimEnd('/'))/api/v1/agent/downloads/windows/$arch" -OutFile $binary
Write-Host 'Detected hardware (this is what KAI will verify):'
& $binary inventory

$capability = Get-WindowsCapability -Online | Where-Object Name -Like 'OpenSSH.Server*'
if ($capability.State -ne 'Installed') { Add-WindowsCapability -Online -Name $capability.Name | Out-Null }
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
if (-not (Get-NetFirewallRule -Name 'KAI-OpenSSH' -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -Name 'KAI-OpenSSH' -DisplayName 'KAI OpenSSH Server' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
}
Write-Host 'SSH service check (this must succeed before enrollment):'
& $binary check
& $binary enroll --api-url $ApiUrl --token $Token --config (Join-Path $data 'config.json')
$action = New-ScheduledTaskAction -Execute $binary -Argument "run --config `"$(Join-Path $data 'config.json')`" --state `"$(Join-Path $data 'leases.json')`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName 'KAI Agent' -Action $action -Trigger $trigger -Settings $settings -User 'SYSTEM' -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName 'KAI Agent'
Write-Host 'KAI Agent 已安装，OpenSSH 和开机任务已经启动。'

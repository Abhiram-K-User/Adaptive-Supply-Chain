<# Explicit opt-in Windows startup task. Run with -WhatIf to inspect registration. #>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$PythonPath,
    [Parameter(Mandatory)][string]$DataDirectory,
    [string]$TaskName = 'ASCI Ingestion',
    [ValidateSet('v0_core', 'v1_corridor')][string]$Scale = 'v1_corridor',
    [ValidateRange(1, 86400)][int]$IntervalSeconds = 60
)
$ErrorActionPreference = 'Stop'
$RepositoryPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$PythonExecutable = (Resolve-Path -LiteralPath $PythonPath).Path
$WorkerScript = Join-Path $RepositoryPath 'scripts\run_ingestion_daemon.py'
$ResolvedDataDirectory = [IO.Path]::GetFullPath($DataDirectory)
$Arguments = '"{0}" --data-dir "{1}" --scale {2} --interval {3}' -f $WorkerScript, $ResolvedDataDirectory, $Scale, $IntervalSeconds
$Action = New-ScheduledTaskAction -Execute $PythonExecutable -Argument $Arguments -WorkingDirectory $RepositoryPath
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable
if ($PSCmdlet.ShouldProcess($TaskName, 'Register startup ingestion worker as the current user')) {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description 'Poll GDACS and PortWatch; durable event and webhook outbox' -User ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -RunLevel Limited
}

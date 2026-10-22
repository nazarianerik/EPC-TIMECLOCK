<#
  TimeClock server control. You normally run this through the .bat files next to it:
    install_autostart.bat    Start the server now and on every boot (run once after setup)
    restart_server.bat       Restart it (e.g. after updating the code or changing config.json)
    stop_server.bat          Stop it until the next reboot
    uninstall_autostart.bat  Stop it and remove the auto-start and firewall rule
#>
param(
    [ValidateSet("install", "uninstall", "start", "stop", "restart")]
    [string]$Action = "restart"
)

$ErrorActionPreference = "Stop"
$TaskName = "TimeClock"
$FirewallRuleName = "TimeClock"
$Root = Split-Path -Parent $PSScriptRoot

# Re-open this script with admin rights if needed (Windows will ask for permission).
$identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" $Action"
    exit
}

function Get-Port {
    $config = Join-Path $Root "data\config.json"
    if (Test-Path $config) {
        $c = Get-Content $config -Raw | ConvertFrom-Json
        if ($c.port) { return [int]$c.port }
    }
    return 8080
}

function Get-LanIp {
    $cfg = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq "Up" } | Select-Object -First 1
    if ($cfg) { return $cfg.IPv4Address.IPAddress }
    return "localhost"
}

function Stop-Server {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $TaskName
    }
    # Make sure nothing is left over: first the restart loop, then Python itself.
    Get-CimInstance Win32_Process -Filter "Name = 'cmd.exe'" |
        Where-Object { $_.CommandLine -like "*start_server.bat*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -like "*serve.py*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Host "Server stopped."
}

function Start-Server {
    Start-ScheduledTask -TaskName $TaskName
    $port = Get-Port
    Write-Host "Starting server..." -NoNewline
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        Write-Host "." -NoNewline
        try {
            Invoke-WebRequest "http://localhost:$port/" -UseBasicParsing -TimeoutSec 3 | Out-Null
            Write-Host ""
            Write-Host "Server is running." -ForegroundColor Green
            $ip = Get-LanIp
            Write-Host "  Employees / NFC tag URL:  http://${ip}:$port/"
            Write-Host "  Admin page:               http://${ip}:$port/admin"
            return
        } catch { }
    }
    Write-Host ""
    Write-Host "The server did not respond within 20 seconds." -ForegroundColor Red
    Write-Host "Look at the end of $Root\data\server.log for the reason."
}

function Install-Server {
    if (-not (Test-Path (Join-Path $Root ".venv\Scripts\python.exe"))) {
        throw "Setup hasn't been run yet. Double-click windows\first_time_setup.bat first."
    }
    if ($Root -match "OneDrive") {
        Write-Host "WARNING: this folder is inside OneDrive. Syncing can damage the database." -ForegroundColor Yellow
        Write-Host "         Moving the folder to C:\TimeClock is strongly recommended." -ForegroundColor Yellow
    }
    Stop-Server

    # 1. Task Scheduler: run the server at every boot, in the background, even when nobody is logged in.
    $bat = Join-Path $PSScriptRoot "start_server.bat"
    $taskAction = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`"" -WorkingDirectory $Root
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $trigger -Principal $principal `
        -Settings $settings -Description "NFC time clock web server ($Root)" -Force | Out-Null
    Write-Host "Auto-start at boot: set up (Task Scheduler task '$TaskName')."

    # 2. Firewall: allow phones on the local network and your Tailscale devices. Nothing else.
    $port = Get-Port
    Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName $FirewallRuleName -Direction Inbound -Action Allow -Protocol TCP `
        -LocalPort $port -RemoteAddress LocalSubnet, "100.64.0.0/10" -Profile Any | Out-Null
    Write-Host "Firewall: port $port opened for the local network and Tailscale."

    # If someone clicked "Cancel" on Windows' "allow Python?" popup, Windows added a rule that
    # blocks Python. Block rules beat allow rules, so remove those.
    Get-NetFirewallRule -Direction Inbound -Action Block -ErrorAction SilentlyContinue |
        Where-Object { ($_ | Get-NetFirewallApplicationFilter).Program -like "*python*.exe" } |
        ForEach-Object {
            Write-Host "Firewall: removing old rule that blocked Python ($($_.DisplayName))."
            $_ | Remove-NetFirewallRule
        }

    # 3. Power: never sleep or hibernate while plugged in (the screen can still turn off).
    powercfg /change standby-timeout-ac 0
    powercfg /change hibernate-timeout-ac 0
    Write-Host "Power: sleep and hibernate turned off (when plugged in)."

    Start-Server
}

function Uninstall-Server {
    Stop-Server
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    Write-Host "Auto-start and firewall rule removed. Your data in the data folder was not touched."
}

try {
    Write-Host "=== TimeClock: $Action ===" -ForegroundColor Cyan
    switch ($Action) {
        "install"   { Install-Server }
        "uninstall" { Uninstall-Server }
        "start"     { Start-Server }
        "stop"      { Stop-Server }
        "restart"   { Stop-Server; Start-Server }
    }
} catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
} finally {
    Write-Host ""
    Read-Host "Press Enter to close"
}

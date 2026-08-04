param(
    [string]$Distro = "",
    [int]$WebUIPort = 8787,
    [int]$RagflowPublicPort = 9222,
    [int]$RagflowWslPort = 8080,
    [string]$ListenAddress = "0.0.0.0",
    [string]$RemoteAddress = "LocalSubnet"
)

$ErrorActionPreference = "Stop"

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    $admin = [Security.Principal.WindowsBuiltInRole]::Administrator
    if (-not $principal.IsInRole($admin)) {
        throw "Run this script from an Administrator PowerShell."
    }
}

function Get-WslIp {
    if ($Distro.Trim()) {
        $output = & wsl.exe -d $Distro hostname -I
    } else {
        $output = & wsl.exe hostname -I
    }
    $ip = ($output -split "\s+" | Where-Object { $_ -match "^\d+\.\d+\.\d+\.\d+$" } | Select-Object -First 1)
    if (-not $ip) {
        throw "Could not detect the WSL IPv4 address. Start the target WSL distro, then rerun this script."
    }
    return $ip
}

function Reset-PortProxy {
    param(
        [int]$ListenPort,
        [int]$ConnectPort,
        [string]$ConnectAddress
    )
    & netsh interface portproxy delete v4tov4 listenaddress=$ListenAddress listenport=$ListenPort | Out-Null
    & netsh interface portproxy add v4tov4 listenaddress=$ListenAddress listenport=$ListenPort connectaddress=$ConnectAddress connectport=$ConnectPort | Out-Null
}

function Reset-FirewallRule {
    param(
        [string]$Name,
        [int]$Port
    )
    $existing = Get-NetFirewallRule -DisplayName $Name -ErrorAction SilentlyContinue
    if ($existing) {
        $existing | Remove-NetFirewallRule
    }
    New-NetFirewallRule `
        -DisplayName $Name `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort $Port `
        -RemoteAddress $RemoteAddress | Out-Null
}

Assert-Administrator

Set-Service iphlpsvc -StartupType Automatic
Start-Service iphlpsvc

$wslIp = Get-WslIp
Write-Host "WSL IPv4: $wslIp"

Reset-PortProxy -ListenPort $WebUIPort -ConnectAddress $wslIp -ConnectPort $WebUIPort
Reset-PortProxy -ListenPort $RagflowPublicPort -ConnectAddress $wslIp -ConnectPort $RagflowWslPort

Reset-FirewallRule -Name "PSKA Demo Hermes WebUI $WebUIPort" -Port $WebUIPort
Reset-FirewallRule -Name "PSKA Demo RAGFlow Web $RagflowPublicPort" -Port $RagflowPublicPort

Write-Host ""
Write-Host "Port proxy:"
& netsh interface portproxy show all

Write-Host ""
Write-Host "Exposed demo URLs on this Windows host:"
Write-Host "  Hermes-WebUI: http://<Windows-LAN-IP>:$WebUIPort/"
Write-Host "  RAGFlow UI:   http://<Windows-LAN-IP>:$RagflowPublicPort/"

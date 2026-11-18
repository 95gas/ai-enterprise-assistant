param(
    [string[]]$Services = @(
        "server",
        "chat-service",
        "auth-service",
        "rag-service",
        "md-maker",
        "md-ingestor",
        "temporal-worker",
        "frontend"
    ),
    [ValidateSet("server", "chat-service", "auth-service", "rag-service", "md-maker", "md-ingestor", "temporal-worker", "frontend")]
    [string]$Service,
    [string]$Theme = "mirai",
    [ValidateSet("cpu", "cuda")]
    [string]$Device = "cpu",
    [switch]$Worker
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSCommandPath
$serverPath = Join-Path $root "server"
$clientPath = Join-Path $root "client"
$secretsEnvPath = Join-Path $serverPath "config\secrets.env"

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path $Path -PathType Leaf)) {
        Write-Warning "Environment file not found at '$Path'; relying on existing environment variables and defaults."
        return
    }

    foreach ($rawLine in Get-Content -Path $Path -Encoding UTF8) {
        $line = $rawLine.Trim()
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) {
            continue
        }
        if ($line.StartsWith("export ")) {
            $line = $line.Substring(7).Trim()
        }

        $eqIndex = $line.IndexOf("=")
        if ($eqIndex -lt 1) {
            continue
        }

        $key = $line.Substring(0, $eqIndex).Trim()
        $val = $line.Substring($eqIndex + 1).Trim()

        if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
            $val = $val.Substring(1, $val.Length - 2)
        }

        # Populate process environment without overriding variables already set in the shell
        $existing = [Environment]::GetEnvironmentVariable($key, "Process")
        if ([string]::IsNullOrEmpty($existing)) {
            [Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}

# Load server/config/secrets.env into the current PowerShell process
Import-DotEnv -Path $secretsEnvPath

$effectiveTheme = if ($PSBoundParameters.ContainsKey("Theme")) { $Theme } elseif ($env:THEME) { $env:THEME } else { $Theme }
$effectiveDevice = if ($PSBoundParameters.ContainsKey("Device")) { $Device } elseif ($env:DEVICE) { $env:DEVICE } else { $Device }

if ($Worker) {
    $Host.UI.RawUI.WindowTitle = "ASK - $Service"
    $env:ENV_FLAG = "prod"
    $env:THEME = $effectiveTheme
    $env:DEVICE = $effectiveDevice
    $env:TEMPORAL_ADDRESS = if ($env:TEMPORAL_ADDRESS) { $env:TEMPORAL_ADDRESS } else { "localhost:7233" }
    $env:TEMPORAL_MICROSERVICES_TASK_QUEUE = if ($env:TEMPORAL_MICROSERVICES_TASK_QUEUE) { $env:TEMPORAL_MICROSERVICES_TASK_QUEUE } else { "demo-microservices" }
    if ($Service -in @("server", "rag-service", "temporal-worker")) {
        $env:TEMPORAL_ENABLED = "true"
    }

    $targetPath = if ($Service -eq "frontend") { $clientPath } else { $serverPath }
    Push-Location $targetPath
    try {
        switch ($Service) {
            "server" {
                $env:PORT = if ($env:SERVER_PORT) { $env:SERVER_PORT } else { "8080" }
                uv run --project $serverPath --locked python app.py
            }
            "chat-service" {
                $env:CHAT_SERVICE_PORT = if ($env:CHAT_SERVICE_PORT) { $env:CHAT_SERVICE_PORT } else { "8001" }
                uv run --project $serverPath --locked python -m src.services.chat.app
            }
            "auth-service" {
                $env:AUTH_SERVICE_PORT = if ($env:AUTH_SERVICE_PORT) { $env:AUTH_SERVICE_PORT } else { "8003" }
                uv run --project $serverPath --locked python -m src.services.authentication.app
            }
            "rag-service" {
                $env:RAG_SERVICE_PORT = if ($env:RAG_SERVICE_PORT) { $env:RAG_SERVICE_PORT } else { "8002" }
                uv run --project $serverPath --locked python -m src.services.rag.app
            }
            "md-maker" {
                $mdMakerPort = if ($env:MD_MAKER_PORT) { $env:MD_MAKER_PORT } else { "8005" }
                uv run --project $serverPath --locked uvicorn src.services.md_maker.app:app --host 0.0.0.0 --port $mdMakerPort
            }
            "md-ingestor" {
                $mdIngestorPort = if ($env:MD_INGESTOR_PORT) { $env:MD_INGESTOR_PORT } else { "8006" }
                uv run --project $serverPath --locked uvicorn src.services.md_ingestor.app:app --host 0.0.0.0 --port $mdIngestorPort
            }
            "temporal-worker" {
                uv run --project $serverPath --locked python -m src.services.temporal.worker
            }
            "frontend" {
                $clientPort = if ($env:CLIENT_PORT) { $env:CLIENT_PORT } else { "5173" }
                yarn dev --host 0.0.0.0 --port $clientPort
            }
            default {
                throw "Unknown service '$Service'."
            }
        }
    }
    finally {
        Pop-Location
    }
    exit $LASTEXITCODE
}

$requiredCommands = @()
if ($Services | Where-Object { $_ -ne "frontend" }) {
    $requiredCommands += "uv"
}
if ("frontend" -in $Services) {
    $requiredCommands += "yarn"
}
foreach ($command in $requiredCommands) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command '$command' was not found on PATH."
    }
}

$configPath = Join-Path $serverPath "config\system.yaml"
if (-not (Test-Path $configPath -PathType Leaf)) {
    throw "Required configuration file '$configPath' is missing."
}

$powerShellCommand = Get-Command powershell.exe -ErrorAction SilentlyContinue
if (-not $powerShellCommand) {
    $powerShellCommand = Get-Command pwsh.exe -ErrorAction SilentlyContinue
}
if (-not $powerShellCommand) {
    throw "Neither powershell.exe nor pwsh.exe was found on PATH."
}

$validServices = @("server", "chat-service", "auth-service", "rag-service", "md-maker", "md-ingestor", "temporal-worker", "frontend")
foreach ($item in $Services) {
    if ($item -notin $validServices) {
        throw "Unknown service '$item'. Valid services: $($validServices -join ', ')."
    }
}

$powerShellExe = $powerShellCommand.Source
foreach ($item in $Services) {
    $arguments = @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-Worker",
        "-Service", $item,
        "-Theme", $effectiveTheme,
        "-Device", $effectiveDevice
    ) -join " "

    Start-Process -FilePath $powerShellExe `
        -ArgumentList $arguments `
        -WorkingDirectory $root | Out-Null
}

Write-Host "Loaded config: $secretsEnvPath"
Write-Host "Started: $($Services -join ', ')"
Write-Host "Theme: $effectiveTheme | Device: $effectiveDevice"
Write-Host "Start PostgreSQL, Neo4j, SeaweedFS S3, Redis, and Temporal before the application services."
$ErrorActionPreference = "Stop"

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Join-Path $RepositoryRoot "code"
$Installer = Join-Path $ProjectRoot "scripts\setup_env.ps1"
$Config = Join-Path $ProjectRoot "configs\setup.yaml"
$Virtualenv = Join-Path $ProjectRoot ".venv"
$HasExplicitVenv = $false

if (-not (Test-Path $Installer -PathType Leaf)) {
    throw "Installer not found: $Installer"
}

for ($index = 0; $index -lt $args.Length; $index++) {
    $arg = $args[$index]
    if ($arg -eq "--venv" -or $arg -like "--venv=*") {
        $HasExplicitVenv = $true
    }
}

if (Test-Path $Virtualenv) {
    $VirtualenvItem = Get-Item -Force $Virtualenv
    if (($VirtualenvItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing symbolic-link virtualenv: $Virtualenv"
    }
}

Push-Location $ProjectRoot
try {
    if ($HasExplicitVenv) {
        & $Installer --config $Config @args
    } else {
        & $Installer --config $Config @args --venv $Virtualenv
    }
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}

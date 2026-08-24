$ErrorActionPreference = "Stop"

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Join-Path $RepositoryRoot "safe_gard_test\code"
$Installer = Join-Path $ProjectRoot "scripts\setup_env.ps1"
$Config = Join-Path $ProjectRoot "configs\setup.yaml"
$Virtualenv = Join-Path $RepositoryRoot ".venv"

if (-not (Test-Path $Installer -PathType Leaf)) {
    throw "Installer not found: $Installer"
}
if (Test-Path $Virtualenv) {
    $VirtualenvItem = Get-Item -Force $Virtualenv
    if (($VirtualenvItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing symbolic-link virtualenv: $Virtualenv"
    }
}

Push-Location $ProjectRoot
try {
    # Keep --venv last so this folder-contract installer always targets the
    # real virtualenv expected at <pipeline>/.venv.
    & $Installer --config $Config @args --venv $Virtualenv
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}

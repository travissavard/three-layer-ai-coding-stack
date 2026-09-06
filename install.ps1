[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $InstallerArgs
)

$ErrorActionPreference = 'Stop'
$UvVersion = '0.12.10'
$UvBaseUrl = "https://github.com/astral-sh/uv/releases/download/$UvVersion"
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("three-layer-installer-" + [guid]::NewGuid())
$ExitCode = 1

New-Item -ItemType Directory -Path $TempRoot | Out-Null

try {
    $env:UV_CACHE_DIR = Join-Path $TempRoot 'cache'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $TempRoot 'python'
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $TempRoot 'project-environment'

    $UvCommand = (Get-Command uv -ErrorAction SilentlyContinue).Source
    if (-not $UvCommand) {
        $Architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
        switch ($Architecture) {
            'X64' {
                $Asset = 'uv-x86_64-pc-windows-msvc.zip'
                $ExpectedHash = 'f65744f94072152b1f86ba2aace4d01f1124d9a8ecb235805039e3718c36cac2'
            }
            'Arm64' {
                $Asset = 'uv-aarch64-pc-windows-msvc.zip'
                $ExpectedHash = 'ee985c51c0c9c1f82267a5d80f959b34a7ff888c109182bd3b2b35c4661bbcde'
            }
            default { throw "Unsupported Windows architecture: $Architecture" }
        }

        $Archive = Join-Path $TempRoot $Asset
        Invoke-WebRequest -Uri "$UvBaseUrl/$Asset" -OutFile $Archive
        $ActualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
        if ($ActualHash -ne $ExpectedHash) {
            throw "uv archive checksum mismatch; expected $ExpectedHash, received $ActualHash"
        }
        $Extracted = Join-Path $TempRoot 'uv'
        Expand-Archive -LiteralPath $Archive -DestinationPath $Extracted
        $UvCommand = (Get-ChildItem -LiteralPath $Extracted -Filter 'uv.exe' -Recurse -File | Select-Object -First 1).FullName
        if (-not $UvCommand) { throw 'Verified uv archive did not contain uv.exe' }
        $env:THREE_LAYER_BOOTSTRAP_UV_DIR = Split-Path -Parent $UvCommand
    }

    & $UvCommand run --frozen --project $PSScriptRoot python -m three_layer_installer @InstallerArgs
    $ExitCode = $LASTEXITCODE
}
finally {
    if (Test-Path -LiteralPath $TempRoot) {
        Remove-Item -LiteralPath $TempRoot -Recurse -Force
    }
}

exit $ExitCode

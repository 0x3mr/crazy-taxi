param([string[]]$CMakeArgs = @())
$ErrorActionPreference = 'Stop'
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) { throw 'CMake 3.20 or newer is required. Install CMake and try again.' }
$Root = Split-Path -Parent $PSScriptRoot
cmake -S $Root -B (Join-Path $Root 'build') -DCMAKE_BUILD_TYPE=Release @CMakeArgs
if ($LASTEXITCODE -ne 0) { throw 'CMake configuration failed.' }
cmake --build (Join-Path $Root 'build') --config Release
if ($LASTEXITCODE -ne 0) { throw 'CMake build failed.' }

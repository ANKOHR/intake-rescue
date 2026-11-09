$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$runtimePath = Join-Path $repoPath '.runtime'
New-Item -ItemType Directory -Force -Path $runtimePath | Out-Null
Copy-Item -LiteralPath (Join-Path $repoPath 'runtime\package.json') -Destination $runtimePath
Copy-Item -LiteralPath (Join-Path $repoPath 'runtime\package-lock.json') -Destination $runtimePath
# Explicit prefix + manifest prevents npm selecting an unrelated ancestor package.
& npm.cmd ci --prefix $runtimePath --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Pinned n8n installation failed' }
Write-Host 'Installed n8n inside the repository .runtime directory.'

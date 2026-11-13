# Run from PowerShell: .\scripts\setup_hybrid.ps1
# Install all declared Python packages, then prefetch the model + tokenizer.
# An already verified model does not contact Hugging Face again.
param(
    [switch]$ForceModel,
    [switch]$VerifyModel
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $projectRoot
try {
    Write-Host '[Hybrid Setup] uv sync: Python dependencies' -ForegroundColor Cyan
    & uv sync
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed ($LASTEXITCODE)" }

    Write-Host '[Hybrid Setup] download/verify local Cross-Encoder model' -ForegroundColor Cyan
    $modelArgs = @('--no-sync', 'python', '-m', 'src.hybrid.prepare_models')
    if ($ForceModel) { $modelArgs += '--force' }
    if ($VerifyModel) { $modelArgs += '--verify' }
    & uv run @modelArgs
    if ($LASTEXITCODE -ne 0) { throw "Hybrid model preparation failed ($LASTEXITCODE)" }

    Write-Host '[Hybrid Setup] Ready. Search uses local-only reranker model.' -ForegroundColor Green
}
finally {
    Pop-Location
}

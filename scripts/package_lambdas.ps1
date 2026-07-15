# Package Lambda deployment artifacts for Terraform.
# Run from repo root:  .\scripts\package_lambdas.ps1
# Agent deps are installed as manylinux wheels so they run on AWS Lambda (Linux).

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Build = Join-Path $Root "infra\build"

New-Item -ItemType Directory -Force -Path $Build | Out-Null

Write-Host "==> Packaging loan-processing"
$LoanSrc = Join-Path $Root "apps\loan-processing\src"
$LoanZip = Join-Path $Build "loan-processing.zip"
if (Test-Path $LoanZip) { Remove-Item $LoanZip -Force }
Compress-Archive -Path (Join-Path $LoanSrc "*") -DestinationPath $LoanZip -Force

Write-Host "==> Packaging agent with Linux-compatible dependencies"
$AgentBuild = Join-Path $Build "agent_pkg"
if (Test-Path $AgentBuild) { Remove-Item $AgentBuild -Recurse -Force }
New-Item -ItemType Directory -Force -Path $AgentBuild | Out-Null

$AgentSrc = Join-Path $Root "agent\src"
Copy-Item -Path (Join-Path $AgentSrc "*") -Destination $AgentBuild -Recurse -Force

# CRITICAL: install manylinux wheels (Lambda is Amazon Linux), not Windows wheels
python -m pip install `
  --quiet `
  --upgrade `
  --target $AgentBuild `
  --platform manylinux2014_x86_64 `
  --implementation cp `
  --python-version 3.12 `
  --only-binary=:all: `
  -r (Join-Path $Root "agent\requirements.txt")

Get-ChildItem -Path $AgentBuild -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $AgentBuild -Recurse -Directory -Filter "*.dist-info" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $AgentBuild -Recurse -Directory -Filter "botocore" -ErrorAction SilentlyContinue | ForEach-Object {
  # keep botocore if pulled in; Lambda provides boto3/botocore but extras are ok
}

$AgentZip = Join-Path $Build "agent.zip"
if (Test-Path $AgentZip) { Remove-Item $AgentZip -Force }

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($AgentBuild, $AgentZip)

$sizeMB = [math]::Round((Get-Item $AgentZip).Length / 1MB, 2)
Write-Host "Created:"
Write-Host "  $LoanZip"
Write-Host "  $AgentZip ($sizeMB MB)"
Write-Host "Next: cd infra; terraform apply -var-file=environments/dev.tfvars"

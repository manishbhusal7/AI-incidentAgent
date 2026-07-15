# Manually invoke the AI incident agent (bypass alarm wait) — ideal for interviews.
# Usage: .\scripts\triage_manual.ps1 -AgentFunctionName ai-incident-triage-agent-dev-agent -AlarmName demo-db-timeout

param(
  [Parameter(Mandatory = $true)][string]$AgentFunctionName,
  [string]$AlarmName = "manual-db-timeout",
  [string]$Reason = "FATAL: connection to loan_db timed out after 5000ms",
  [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"

# Fail fast if AWS CLI is not authenticated
$identity = aws sts get-caller-identity --region $Region 2>$null
if (-not $identity) {
  Write-Error @"
AWS credentials not found in this terminal.

Run:
  aws configure
(enter Access Key ID, Secret Access Key, region us-east-1, output json)

Then re-run the demo.
"@
}

$payload = @{
  manual     = $true
  alarm_name = $AlarmName
  state      = "ALARM"
  reason     = $Reason
  scenario   = "db_timeout"
} | ConvertTo-Json -Compress

$tmp = Join-Path $env:TEMP "triage-payload.json"
# AWS CLI on Windows can mishandle UTF-8 BOM; use ASCII
Set-Content -Path $tmp -Value $payload -Encoding ascii

$out = Join-Path $env:TEMP "triage-response.json"
if (Test-Path $out) { Remove-Item $out -Force }

aws lambda invoke `
  --function-name $AgentFunctionName `
  --region $Region `
  --cli-binary-format raw-in-base64-out `
  --payload "file://$tmp" `
  $out

if (-not (Test-Path $out)) {
  Write-Error "Lambda invoke produced no response file. Check AWS credentials and function name."
}

Write-Host "Lambda response:"
Get-Content $out -Raw

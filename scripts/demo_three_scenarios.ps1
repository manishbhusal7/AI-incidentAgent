# Three interview demos:
#   1) False alarm     -> no_action
#   2) Recoverable     -> restart_service (auto-approved + executed)
#   3) Dangerous       -> delete_database BLOCKED
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\scripts\demo_three_scenarios.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\demo_three_scenarios.ps1 -Scenario 2

param(
  [ValidateSet("all", "1", "2", "3")]
  [string]$Scenario = "all",
  [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"
$Infra = Join-Path (Split-Path -Parent $PSScriptRoot) "infra"

Push-Location $Infra
try {
  $Api = terraform output -raw api_endpoint
  $Agent = terraform output -raw agent_function_name
  $Bucket = terraform output -raw artifacts_bucket
  $Alarm = terraform output -raw errors_alarm_name
  $Loan = terraform output -raw loan_function_name
} finally {
  Pop-Location
}

$identity = aws sts get-caller-identity --region $Region 2>$null
if (-not $identity) {
  Write-Error "AWS credentials missing. Run: aws configure"
}

function Invoke-AgentDemo {
  param(
    [string]$DemoScenario,
    [string]$Reason
  )

  $payloadObj = @{
    manual        = $true
    demo_scenario = $DemoScenario
    alarm_name    = $Alarm
    state         = "ALARM"
    reason        = $Reason
  }
  $payload = $payloadObj | ConvertTo-Json -Compress

  $tmp = Join-Path $env:TEMP ("demo-" + $DemoScenario + "-payload.json")
  $out = Join-Path $env:TEMP ("demo-" + $DemoScenario + "-response.json")
  Set-Content -Path $tmp -Value $payload -Encoding ascii
  if (Test-Path $out) { Remove-Item $out -Force }

  aws lambda invoke `
    --function-name $Agent `
    --region $Region `
    --cli-binary-format raw-in-base64-out `
    --payload ("file://" + $tmp) `
    $out | Out-Null

  $raw = Get-Content $out -Raw
  Write-Host $raw
  return ($raw | ConvertFrom-Json)
}

function Show-Banner {
  param([string]$Title)
  Write-Host ""
  Write-Host "============================================================"
  Write-Host $Title
  Write-Host "============================================================"
}

if (($Scenario -eq "all") -or ($Scenario -eq "1")) {
  Show-Banner "DEMO 1: False Alarm -> no_action"
  Write-Host "Trigger: /chaos/false_alarm (transient blip that recovers)"
  try {
    Invoke-RestMethod -Uri ($Api + "/chaos/false_alarm") -Method POST | ConvertTo-Json -Compress
  } catch {
    Write-Host $_.Exception.Message
  }

  $r = Invoke-AgentDemo -DemoScenario "false_alarm" -Reason "Transient blip recovered; false alarm check"
  Write-Host ""
  Write-Host (">>> recommended_action: " + $r.report.recommended_action)
  Write-Host (">>> confidence: " + $r.report.confidence_score)
  Write-Host (">>> guardrail approved: " + $r.guardrail.approved + " executed: " + $r.guardrail.executed)
  Write-Host (">>> report: " + $r.persisted.md_key)
}

if (($Scenario -eq "all") -or ($Scenario -eq "2")) {
  Show-Banner "DEMO 2: Recoverable Incident -> restart_service (AUTO EXECUTE)"
  Write-Host "Trigger: /simulate-error (DB connection pool exhausted)"
  try {
    Invoke-WebRequest -Uri ($Api + "/simulate-error") -Method POST -UseBasicParsing | Out-Null
  } catch {
    if ($_.Exception.Response) {
      Write-Host ("Expected failure: " + [int]$_.Exception.Response.StatusCode)
    } else {
      Write-Host $_.Exception.Message
    }
  }

  $before = aws lambda get-function-configuration `
    --function-name $Loan `
    --region $Region `
    --query "Environment.Variables.RESTART_TOKEN" `
    --output text

  $r = Invoke-AgentDemo -DemoScenario "recoverable" -Reason "FATAL: connection pool exhausted after 5000ms"
  Write-Host ""
  Write-Host (">>> recommended_action: " + $r.report.recommended_action)
  Write-Host (">>> confidence: " + $r.report.confidence_score)
  Write-Host (">>> guardrail approved: " + $r.guardrail.approved + " executed: " + $r.guardrail.executed)
  Write-Host (">>> execution_result: " + ($r.guardrail.execution_result | ConvertTo-Json -Compress))

  $after = aws lambda get-function-configuration `
    --function-name $Loan `
    --region $Region `
    --query "Environment.Variables.RESTART_TOKEN" `
    --output text

  Write-Host (">>> RESTART_TOKEN before=" + $before + " after=" + $after)
  if ($after -ne $before) {
    Write-Host ">>> SUCCESS: service restart executed (env token bumped)"
  } else {
    Write-Host ">>> NOTE: token unchanged - check AUTO_EXECUTE_APPROVED / IAM"
  }
  Write-Host (">>> report: " + $r.persisted.md_key)
}

if (($Scenario -eq "all") -or ($Scenario -eq "3")) {
  Show-Banner "DEMO 3: Dangerous Incident -> delete_database BLOCKED"
  Write-Host "Adversarial demo: model recommends delete_database at 99% confidence"

  $r = Invoke-AgentDemo -DemoScenario "dangerous" -Reason "Critical DB corruption - model proposes wipe"
  Write-Host ""
  Write-Host (">>> recommended_action: " + $r.report.recommended_action)
  Write-Host (">>> confidence: " + $r.report.confidence_score)
  Write-Host (">>> guardrail approved: " + $r.guardrail.approved)
  Write-Host (">>> requires_human_approval: " + $r.guardrail.requires_human_approval)
  Write-Host (">>> executed: " + $r.guardrail.executed)
  Write-Host (">>> reason: " + $r.guardrail.reason)
  Write-Host (">>> report: " + $r.persisted.md_key)
}

Write-Host ""
Write-Host ("All selected demos complete. Reports in s3://" + $Bucket + "/incidents/")
aws s3 ls ("s3://" + $Bucket + "/incidents/") --region $Region | Select-Object -Last 6

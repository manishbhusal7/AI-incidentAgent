# Verify stack resources via AWS CLI and optionally destroy.
# Usage:
#   .\scripts\smoke_verify.ps1
#   .\scripts\smoke_verify.ps1 -Destroy

param(
  [string]$Region = "us-east-1",
  [switch]$Destroy
)

$ErrorActionPreference = "Stop"
$Infra = Join-Path (Split-Path -Parent $PSScriptRoot) "infra"
Push-Location $Infra

$Loan = terraform output -raw loan_function_name
$Agent = terraform output -raw agent_function_name
$Bucket = terraform output -raw artifacts_bucket
$Api = terraform output -raw api_endpoint
$ErrAlarm = terraform output -raw errors_alarm_name

Write-Host "API: $Api"
aws lambda get-function --function-name $Loan --region $Region --query "Configuration.[FunctionName,Runtime,LastModified]" --output table
aws lambda get-function --function-name $Agent --region $Region --query "Configuration.[FunctionName,Runtime,Timeout]" --output table
aws cloudwatch describe-alarms --alarm-names $ErrAlarm --region $Region --query "MetricAlarms[].{Name:AlarmName,State:StateValue}" --output table
aws s3 ls "s3://$Bucket/" --region $Region
Invoke-RestMethod -Uri "$Api/health" | ConvertTo-Json

if ($Destroy) {
  Write-Host "Destroying stack..."
  terraform destroy -var-file=environments/dev.tfvars -auto-approve
}

Pop-Location

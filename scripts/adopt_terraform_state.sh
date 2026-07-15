#!/usr/bin/env bash
# Import AWS resources that already exist but are missing from Terraform state.
# Safe to re-run: skips addresses already in state and ignores missing resources.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA="${ROOT}/infra"
VAR_FILE="${INFRA}/environments/dev.tfvars"
REGION="${AWS_REGION:-us-east-1}"
PROJECT="${TF_VAR_project_name:-ai-incident-triage-agent}"
ENV="${TF_VAR_environment:-dev}"
PREFIX="${PROJECT}-${ENV}"

cd "${INFRA}"

try_import() {
  local addr="$1"
  local id="$2"
  if terraform state show "${addr}" >/dev/null 2>&1; then
    return 0
  fi
  echo "Importing ${addr} ..."
  terraform import -var-file="${VAR_FILE}" "${addr}" "${id}" || echo "  skipped ${addr}"
}

account_id="$(aws sts get-caller-identity --query Account --output text)"

try_import aws_ssm_parameter.anthropic_api_key "/${PROJECT}/${ENV}/anthropic_api_key"
try_import aws_ssm_parameter.claude_usage "/${PROJECT}/${ENV}/claude_usage"

try_import aws_iam_role.loan "${PREFIX}-loan-role"
try_import aws_iam_role.agent "${PREFIX}-agent-role"
try_import aws_iam_role_policy.loan "${PREFIX}-loan-role:${PREFIX}-loan-policy"
try_import aws_iam_role_policy.agent "${PREFIX}-agent-role:${PREFIX}-agent-policy"

try_import aws_cloudwatch_log_group.loan "/aws/lambda/${PREFIX}-loan-processing"
try_import aws_cloudwatch_log_group.agent "/aws/lambda/${PREFIX}-agent"

try_import aws_sns_topic.incidents "arn:aws:sns:${REGION}:${account_id}:${PREFIX}-incidents"

try_import aws_cloudwatch_metric_alarm.errors "${PREFIX}-errors"
try_import aws_cloudwatch_metric_alarm.latency "${PREFIX}-latency"
try_import aws_cloudwatch_event_rule.alarm_to_agent "${PREFIX}-alarm-to-agent"
try_import aws_cloudwatch_dashboard.main "${PREFIX}"

bucket="$(aws s3api list-buckets --query "Buckets[?starts_with(Name, 'aita-${ENV}-art-')].Name | [-1]" --output text 2>/dev/null || true)"
if [[ -n "${bucket}" && "${bucket}" != "None" ]]; then
  try_import aws_s3_bucket.artifacts "${bucket}"
  try_import aws_s3_bucket_public_access_block.artifacts "${bucket}"
  try_import aws_s3_bucket_lifecycle_configuration.artifacts "${bucket}"
  try_import aws_s3_object.initial_deploy "${bucket}/deploys/000-initial.json"
fi

api_id="$(aws apigatewayv2 get-apis --query "Items[?Name=='${PREFIX}-http'].ApiId | [0]" --output text 2>/dev/null || true)"
if [[ -n "${api_id}" && "${api_id}" != "None" ]]; then
  try_import aws_apigatewayv2_api.http "${api_id}"
  try_import aws_apigatewayv2_stage.default "${api_id}/\$default"

  integration_id="$(aws apigatewayv2 get-integrations --api-id "${api_id}" --query "Items[0].IntegrationId" --output text 2>/dev/null || true)"
  if [[ -n "${integration_id}" && "${integration_id}" != "None" ]]; then
    try_import aws_apigatewayv2_integration.loan "${api_id}/${integration_id}"
  fi

  route_id="$(aws apigatewayv2 get-routes --api-id "${api_id}" --query "Items[?RouteKey=='\$default'].RouteId | [0]" --output text 2>/dev/null || true)"
  if [[ -n "${route_id}" && "${route_id}" != "None" ]]; then
    try_import aws_apigatewayv2_route.proxy "${api_id}/${route_id}"
  fi
fi

try_import aws_lambda_function.loan "${PREFIX}-loan-processing"
try_import aws_lambda_function.agent "${PREFIX}-agent"
try_import aws_lambda_function_event_invoke_config.loan "${PREFIX}-loan-processing"
try_import aws_lambda_permission.apigw "${PREFIX}-loan-processing/AllowAPIGatewayInvoke"
try_import aws_lambda_permission.eventbridge "${PREFIX}-agent/AllowEventBridgeInvoke"
try_import aws_cloudwatch_event_target.agent "${PREFIX}-alarm-to-agent/IncidentAgent"

echo "Adopt complete."

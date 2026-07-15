output "api_endpoint" {
  description = "Loan Processing HTTP API base URL"
  value       = aws_apigatewayv2_api.http.api_endpoint
}

output "loan_function_name" {
  value = aws_lambda_function.loan.function_name
}

output "agent_function_name" {
  value = aws_lambda_function.agent.function_name
}

output "artifacts_bucket" {
  value = aws_s3_bucket.artifacts.bucket
}

output "sns_topic_arn" {
  value = aws_sns_topic.incidents.arn
}

output "loan_log_group" {
  value = aws_cloudwatch_log_group.loan.name
}

output "errors_alarm_name" {
  value = aws_cloudwatch_metric_alarm.errors.alarm_name
}

output "latency_alarm_name" {
  value = aws_cloudwatch_metric_alarm.latency.alarm_name
}

output "anthropic_ssm_param" {
  value = aws_ssm_parameter.anthropic_api_key.name
}

output "dashboard_name" {
  value = aws_cloudwatch_dashboard.main.dashboard_name
}

output "verify_commands" {
  description = "Copy-paste AWS CLI verification commands"
  value       = <<-EOT
    aws lambda get-function --function-name ${aws_lambda_function.loan.function_name}
    aws lambda get-function --function-name ${aws_lambda_function.agent.function_name}
    aws apigatewayv2 get-apis
    aws logs describe-log-groups --log-group-name-prefix ${aws_cloudwatch_log_group.loan.name}
    aws cloudwatch describe-alarms --alarm-names ${aws_cloudwatch_metric_alarm.errors.alarm_name} ${aws_cloudwatch_metric_alarm.latency.alarm_name}
    aws s3 ls s3://${aws_s3_bucket.artifacts.bucket}/
    aws ssm get-parameter --name ${aws_ssm_parameter.anthropic_api_key.name} --with-decryption
  EOT
}

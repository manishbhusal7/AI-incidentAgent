locals {
  name_prefix = "${var.project_name}-${var.environment}"
  metric_ns   = "LoanProcessing"
}

# ---------------------------------------------------------------------------
# Storage — incident reports + deploy registry
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "artifacts" {
  # bucket_prefix max length is 37
  bucket_prefix = "aita-${var.environment}-art-"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "expire-old-artifacts"
    status = "Enabled"

    filter {
      prefix = ""
    }

    expiration {
      days = 30
    }
  }
}

resource "aws_s3_object" "initial_deploy" {
  bucket       = aws_s3_bucket.artifacts.id
  key          = "deploys/000-initial.json"
  content_type = "application/json"
  content = jsonencode({
    version      = "0.1.0"
    git_sha      = "initial"
    timestamp    = timestamp()
    change_notes = "Initial terraform apply bootstrap deploy marker"
    service      = "loan-processing"
  })
}

# ---------------------------------------------------------------------------
# Secrets / config — SSM SecureString (near-zero cost)
# ---------------------------------------------------------------------------
resource "aws_ssm_parameter" "anthropic_api_key" {
  name        = "/${var.project_name}/${var.environment}/anthropic_api_key"
  description = "Anthropic Claude API key for incident agent"
  type        = "SecureString"
  value       = var.anthropic_api_key != "" ? var.anthropic_api_key : "REPLACE_ME"
  overwrite   = true

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "claude_usage" {
  name        = "/${var.project_name}/${var.environment}/claude_usage"
  description = "Monthly Claude usage counter YYYY-MM:count"
  type        = "String"
  value       = "1970-01:0"
  overwrite   = true

  lifecycle {
    ignore_changes = [value]
  }
}

# ---------------------------------------------------------------------------
# SNS — human approval / notifications
# ---------------------------------------------------------------------------
resource "aws_sns_topic" "incidents" {
  name = "${local.name_prefix}-incidents"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.notification_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.incidents.arn
  protocol  = "email"
  endpoint  = var.notification_email
}

# ---------------------------------------------------------------------------
# Lambda packages
# ---------------------------------------------------------------------------
data "archive_file" "loan_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../apps/loan-processing/src"
  output_path = "${path.module}/build/loan-processing.zip"
}

data "archive_file" "agent_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../agent/src"
  output_path = "${path.module}/build/agent-src.zip"
}

locals {
  agent_package_path = fileexists("${path.module}/build/agent.zip") ? "${path.module}/build/agent.zip" : data.archive_file.agent_zip.output_path
  agent_package_hash = fileexists("${path.module}/build/agent.zip") ? filebase64sha256("${path.module}/build/agent.zip") : data.archive_file.agent_zip.output_base64sha256
}

# ---------------------------------------------------------------------------
# IAM — Loan Processing Lambda
# ---------------------------------------------------------------------------
resource "aws_iam_role" "loan" {
  name = "${local.name_prefix}-loan-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "loan" {
  name = "${local.name_prefix}-loan-policy"
  role = aws_iam_role.loan.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Logs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:*:log-group:/aws/lambda/${local.name_prefix}-loan-processing*"
      },
      {
        Sid      = "EMFMetrics"
        Effect   = "Allow"
        Action   = ["cloudwatch:PutMetricData"]
        Resource = "*"
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = local.metric_ns
          }
        }
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "loan" {
  name              = "/aws/lambda/${local.name_prefix}-loan-processing"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "loan" {
  function_name    = "${local.name_prefix}-loan-processing"
  role             = aws_iam_role.loan.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.loan_zip.output_path
  source_code_hash = data.archive_file.loan_zip.output_base64sha256
  timeout          = 15
  memory_size      = 256

  environment {
    variables = {
      DEMO_MODE             = var.demo_mode ? "true" : "false"
      METRIC_NAMESPACE      = local.metric_ns
      SERVICE_NAME          = "loan-processing"
      DEPLOY_VERSION        = "1.0.0"
      CHAOS_LATENCY_SECONDS = "3"
      RESTART_TOKEN         = "0"
    }
  }

  depends_on = [aws_cloudwatch_log_group.loan]
}

resource "aws_lambda_function_event_invoke_config" "loan" {
  function_name          = aws_lambda_function.loan.function_name
  maximum_retry_attempts = 0
}

# ---------------------------------------------------------------------------
# API Gateway HTTP API
# ---------------------------------------------------------------------------
resource "aws_apigatewayv2_api" "http" {
  name          = "${local.name_prefix}-http"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "loan" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.loan.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "proxy" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.loan.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.loan.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}

# ---------------------------------------------------------------------------
# CloudWatch Alarms — EventBridge picks up ALARM transitions
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${local.name_prefix}-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "LoanErrors"
  namespace           = local.metric_ns
  period              = 60
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_description   = "Fires when loan app emits >=1 LoanErrors in 1 minute"
  dimensions = {
    Service = "loan-processing"
  }
}

resource "aws_cloudwatch_metric_alarm" "latency" {
  alarm_name          = "${local.name_prefix}-latency"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ProcessingLatencyMs"
  namespace           = local.metric_ns
  period              = 60
  statistic           = "Average"
  threshold           = 2000
  treat_missing_data  = "notBreaching"
  alarm_description   = "Fires when average processing latency > 2s"
  dimensions = {
    Service = "loan-processing"
  }
}

# ---------------------------------------------------------------------------
# IAM — Agent Lambda (least privilege, no delete/IAM mutate)
# ---------------------------------------------------------------------------
resource "aws_iam_role" "agent" {
  name = "${local.name_prefix}-agent-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "agent" {
  name = "${local.name_prefix}-agent-policy"
  role = aws_iam_role.agent.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "LogsWrite"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:*:log-group:/aws/lambda/${local.name_prefix}-agent*"
      },
      {
        Sid    = "ReadAppLogs"
        Effect = "Allow"
        Action = [
          "logs:FilterLogEvents",
          "logs:DescribeLogStreams",
          "logs:GetLogEvents"
        ]
        Resource = [
          aws_cloudwatch_log_group.loan.arn,
          "${aws_cloudwatch_log_group.loan.arn}:*"
        ]
      },
      {
        Sid    = "ReadMetricsAndAlarms"
        Effect = "Allow"
        Action = [
          "cloudwatch:GetMetricData",
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:DescribeAlarms"
        ]
        Resource = "*"
      },
      {
        Sid    = "ArtifactsRW"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.artifacts.arn,
          "${aws_s3_bucket.artifacts.arn}/*"
        ]
      },
      {
        Sid      = "SsmReadKey"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = aws_ssm_parameter.anthropic_api_key.arn
      },
      {
        Sid      = "SsmUsageCounter"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:PutParameter"]
        Resource = aws_ssm_parameter.claude_usage.arn
      },
      {
        Sid      = "SnsNotify"
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = aws_sns_topic.incidents.arn
      },
      {
        Sid    = "SafeRemediation"
        Effect = "Allow"
        Action = [
          "lambda:GetFunctionConfiguration",
          "lambda:UpdateFunctionConfiguration",
          "lambda:GetFunctionConcurrency",
          "lambda:PutFunctionConcurrency"
        ]
        Resource = aws_lambda_function.loan.arn
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "agent" {
  name              = "/aws/lambda/${local.name_prefix}-agent"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "agent" {
  function_name    = "${local.name_prefix}-agent"
  role             = aws_iam_role.agent.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  filename         = local.agent_package_path
  source_code_hash = local.agent_package_hash
  timeout          = 120
  memory_size      = 512

  environment {
    variables = {
      ARTIFACTS_BUCKET           = aws_s3_bucket.artifacts.bucket
      DEPLOY_PREFIX              = "deploys/"
      REPORT_PREFIX              = "incidents/"
      LOAN_LOG_GROUP             = aws_cloudwatch_log_group.loan.name
      LOAN_FUNCTION_NAME         = aws_lambda_function.loan.function_name
      METRIC_NAMESPACE           = local.metric_ns
      SERVICE_NAME               = "loan-processing"
      PRIMARY_ALARM_NAME         = aws_cloudwatch_metric_alarm.errors.alarm_name
      SNS_TOPIC_ARN              = aws_sns_topic.incidents.arn
      ANTHROPIC_API_KEY_PARAM    = aws_ssm_parameter.anthropic_api_key.name
      USAGE_COUNTER_PARAM        = aws_ssm_parameter.claude_usage.name
      MAX_CLAUDE_CALLS_PER_MONTH = tostring(var.max_claude_calls_per_month)
      CLAUDE_MODEL               = var.claude_model
      MAX_TOOL_ROUNDS            = "4"
      MAX_LOG_EVENTS             = "50"
      AUTO_EXECUTE_APPROVED      = var.auto_execute_approved ? "true" : "false"
      MAX_SCALE_CEILING          = "3"
      MIN_SCALE_FLOOR            = "1"
      USAGE_FAIL_CLOSED          = "false"
    }
  }

  depends_on = [aws_cloudwatch_log_group.agent]
}

# ---------------------------------------------------------------------------
# EventBridge — Alarm ALARM state -> Agent Lambda
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_event_rule" "alarm_to_agent" {
  name        = "${local.name_prefix}-alarm-to-agent"
  description = "Invoke AI incident agent when loan alarms enter ALARM state"

  event_pattern = jsonencode({
    source      = ["aws.cloudwatch"]
    detail-type = ["CloudWatch Alarm State Change"]
    detail = {
      alarmName = [
        aws_cloudwatch_metric_alarm.errors.alarm_name,
        aws_cloudwatch_metric_alarm.latency.alarm_name
      ]
      state = {
        value = ["ALARM"]
      }
    }
  })
}

resource "aws_cloudwatch_event_target" "agent" {
  rule      = aws_cloudwatch_event_rule.alarm_to_agent.name
  target_id = "IncidentAgent"
  arn       = aws_lambda_function.agent.arn
}

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.agent.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.alarm_to_agent.arn
}

# ---------------------------------------------------------------------------
# Dashboard (free) for interview demos
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = local.name_prefix
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Loan Errors"
          region  = var.aws_region
          metrics = [[local.metric_ns, "LoanErrors", "Service", "loan-processing"]]
          period  = 60
          stat    = "Sum"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Processing Latency (avg)"
          region  = var.aws_region
          metrics = [[local.metric_ns, "ProcessingLatencyMs", "Service", "loan-processing"]]
          period  = 60
          stat    = "Average"
        }
      }
    ]
  })
}

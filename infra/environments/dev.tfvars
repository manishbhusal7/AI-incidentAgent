aws_region                 = "us-east-1"
project_name               = "ai-incident-triage-agent"
environment                = "dev"
demo_mode                  = true
notification_email         = ""
claude_model               = "claude-haiku-4-5-20251001"
max_claude_calls_per_month = 50
log_retention_days         = 7
auto_execute_approved      = true
# Set via: terraform apply -var="anthropic_api_key=$env:ANTHROPIC_API_KEY"
# anthropic_api_key       = ""

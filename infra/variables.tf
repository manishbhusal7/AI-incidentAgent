variable "aws_region" {
  type        = string
  description = "AWS region for all resources"
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  description = "Project name prefix"
  default     = "ai-incident-triage-agent"
}

variable "environment" {
  type        = string
  description = "Environment name"
  default     = "dev"
}

variable "demo_mode" {
  type        = bool
  description = "Enable chaos endpoints"
  default     = true
}

variable "notification_email" {
  type        = string
  description = "Optional email for SNS human-approval notifications (empty to skip subscription)"
  default     = ""
}

variable "anthropic_api_key" {
  type        = string
  description = "Anthropic API key stored in SSM SecureString (sensitive). Leave empty to set later."
  default     = ""
  sensitive   = true
}

variable "claude_model" {
  type        = string
  description = "Claude model id"
  default     = "claude-haiku-4-5-20251001"
}

variable "max_claude_calls_per_month" {
  type        = number
  description = "Hard monthly budget for Claude invocations"
  default     = 50
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch log retention"
  default     = 7
}

variable "auto_execute_approved" {
  type        = bool
  description = "Whether guardrail-approved actions execute automatically"
  default     = true
}

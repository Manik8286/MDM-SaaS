variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "ap-south-1"
}

variable "environment" {
  description = "Deployment environment (production, staging, development)"
  type        = string
  default     = "production"
}

variable "app_name" {
  description = "Application name used as a prefix for all resources"
  type        = string
  default     = "mdm-saas"
}

variable "domain_name" {
  description = "Primary domain name for the MDM server, e.g. mdm.company.io"
  type        = string
}

variable "route53_zone_id" {
  description = "Route 53 hosted zone ID for the domain"
  type        = string
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "db_multi_az" {
  description = "Enable Multi-AZ for RDS (recommended for production)"
  type        = bool
  default     = true
}

variable "db_allocated_storage" {
  description = "Allocated storage in GB for the RDS instance"
  type        = number
  default     = 20
}

variable "api_task_cpu" {
  description = "CPU units for the API ECS task (1024 = 1 vCPU)"
  type        = number
  default     = 512
}

variable "api_task_memory" {
  description = "Memory in MB for the API ECS task"
  type        = number
  default     = 1024
}

variable "api_desired_count" {
  description = "Desired number of API ECS task instances"
  type        = number
  default     = 2
}

variable "worker_task_cpu" {
  description = "CPU units for the SQS worker ECS task"
  type        = number
  default     = 256
}

variable "worker_task_memory" {
  description = "Memory in MB for the SQS worker ECS task"
  type        = number
  default     = 512
}

variable "apns_use_sandbox" {
  description = "Use APNs sandbox endpoint (true for development, false for production)"
  type        = bool
  default     = false
}

variable "alert_email" {
  description = "Email address to receive CloudWatch alarm notifications (leave empty to disable)"
  type        = string
  default     = ""
}

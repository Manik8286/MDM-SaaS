terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Create bucket/table with scripts/tf_bootstrap.sh before first apply
  # NOTE: backend blocks do not support variable interpolation; values must be
  # literal strings. Override via `terraform init -backend-config=...` flags
  # or a backend.hcl file if you need different values.
  backend "s3" {
    bucket         = "mdm-saas-terraform-state"
    key            = "production/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "mdm-saas-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      Project     = var.app_name
      ManagedBy   = "terraform"
    }
  }
}

locals {
  common_name = "${var.app_name}-${var.environment}"
}

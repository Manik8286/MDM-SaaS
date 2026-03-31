output "ecr_repository_url" {
  description = "URL of the ECR repository to push Docker images to"
  value       = aws_ecr_repository.app.repository_url
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.main.dns_name
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (host:port)"
  value       = aws_db_instance.main.endpoint
  sensitive   = true
}

output "api_service_name" {
  description = "Name of the ECS service running the API tasks"
  value       = aws_ecs_service.api.name
}

output "worker_service_name" {
  description = "Name of the ECS service running the SQS worker tasks"
  value       = aws_ecs_service.worker.name
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "aws_region" {
  description = "AWS region where resources were deployed"
  value       = var.aws_region
}

output "deployment_instructions" {
  description = "Next steps after terraform apply"
  value       = <<-EOT
  =========================================================
  MDM SaaS - Deployment Complete
  =========================================================

  1. Push your first Docker image:
     $(terraform output -raw ecr_repository_url)

     aws ecr get-login-password --region ${var.aws_region} \
       | docker login --username AWS \
         --password-stdin $(terraform output -raw ecr_repository_url)

     docker build -t mdm-saas .
     docker tag mdm-saas:latest $(terraform output -raw ecr_repository_url):latest
     docker push $(terraform output -raw ecr_repository_url):latest

  2. Upload certificates to Secrets Manager (first time only):
     cd /path/to/repo
     APP_NAME=${var.app_name} AWS_REGION=${var.aws_region} \
       ENVIRONMENT=${var.environment} bash scripts/upload_secrets.sh

  3. Force a new ECS deployment to pick up the pushed image:
     aws ecs update-service \
       --cluster ${aws_ecs_cluster.main.name} \
       --service ${aws_ecs_service.api.name} \
       --force-new-deployment

     aws ecs update-service \
       --cluster ${aws_ecs_cluster.main.name} \
       --service ${aws_ecs_service.worker.name} \
       --force-new-deployment

  4. Verify the API health check:
     curl https://${var.domain_name}/healthz

  5. Future deployments are handled automatically by the GitHub Actions
     workflow (.github/workflows/deploy.yml) on every push to main.

  GitHub Actions secrets to configure in your repository:
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    AWS_REGION       = ${var.aws_region}
    ECR_REPOSITORY   = $(terraform output -raw ecr_repository_url)
    ECS_CLUSTER      = ${aws_ecs_cluster.main.name}
    ECS_API_SERVICE  = ${aws_ecs_service.api.name}
    ECS_WORKER_SERVICE = ${aws_ecs_service.worker.name}
    SUBNET_ID        = (one of the private subnet IDs)
    ECS_SECURITY_GROUP_ID = (the ECS security group ID)
  =========================================================
  EOT
}

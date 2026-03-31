# strativon.click — MDM SaaS production deployment
# Budget-optimised: ~$50/month

aws_region   = "ap-south-1"
app_name     = "mdm-saas"
environment  = "production"

domain_name    = "mdm.strativon.click"
route53_zone_id = "Z020329117J90S5LJY1QC"

# Budget config (single-AZ, small instances)
db_instance_class    = "db.t3.micro"
db_multi_az          = false
db_allocated_storage = 20

# ECS — single API task, minimal sizes
api_task_cpu      = 256
api_task_memory   = 512
api_desired_count = 1

worker_task_cpu    = 256
worker_task_memory = 512

apns_use_sandbox = false

# strativon.click — MDM SaaS production deployment
# Budget-optimised: ~$50/month

aws_region  = "ap-south-1"
app_name    = "mdm-saas"
environment = "production"

domain_name     = "mdm.strativon.click"
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

# --- Fill in before applying — no defaults, terraform will fail without them ---
dashboard_url           = "https://REPLACE_WITH_DASHBOARD_URL"
smtp_host               = "REPLACE_WITH_SMTP_HOST"       # e.g. email-smtp.ap-south-1.amazonaws.com (SES)
smtp_username           = "REPLACE_WITH_SMTP_USERNAME"   # e.g. SES SMTP IAM access key ID
smtp_from_email         = "REPLACE_WITH_VERIFIED_SENDER" # must be a verified sending identity
stripe_starter_price_id = "REPLACE_WITH_STRIPE_LIVE_PRICE_ID"
stripe_pro_price_id     = "REPLACE_WITH_STRIPE_LIVE_PRICE_ID"
# Actual secret values (SMTP password, Stripe keys, APNs/MDM certs) are NOT
# set here — they go to Secrets Manager via scripts/upload_secrets.sh after
# terraform apply creates the placeholder secrets.

# ---------------------------------------------------------------------------
# Random password for the RDS master user
# ---------------------------------------------------------------------------

resource "random_password" "db_password" {
  length  = 32
  special = false
}

# ---------------------------------------------------------------------------
# DB subnet group (private subnets only)
# ---------------------------------------------------------------------------

resource "aws_db_subnet_group" "main" {
  name        = "${local.common_name}-db-subnet-group"
  description = "Private subnets for ${local.common_name} RDS"
  subnet_ids  = [aws_subnet.private_a.id, aws_subnet.private_b.id]

  tags = {
    Name = "${local.common_name}-db-subnet-group"
  }
}

# ---------------------------------------------------------------------------
# Security group - allow inbound 5432 from ECS tasks only
# ---------------------------------------------------------------------------

resource "aws_security_group" "rds" {
  name        = "${local.common_name}-rds-sg"
  description = "Allow PostgreSQL access from ECS tasks"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from ECS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.common_name}-rds-sg"
  }
}

# ---------------------------------------------------------------------------
# RDS PostgreSQL instance
# ---------------------------------------------------------------------------

resource "aws_db_instance" "main" {
  identifier        = "${local.common_name}-postgres"
  engine            = "postgres"
  engine_version    = "16"
  instance_class    = var.db_instance_class
  allocated_storage = var.db_allocated_storage

  db_name  = "mdmdb"
  username = "mdm"
  password = random_password.db_password.result

  multi_az               = var.db_multi_az
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  skip_final_snapshot       = false
  final_snapshot_identifier = "${local.common_name}-final"

  storage_encrypted            = true
  backup_retention_period      = 7
  deletion_protection          = true
  performance_insights_enabled = true

  tags = {
    Name = "${local.common_name}-postgres"
  }
}

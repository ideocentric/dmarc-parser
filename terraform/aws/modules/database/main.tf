# ── split_vm: PostgreSQL on EC2 in the private subnet ─────────────────────────

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

resource "aws_instance" "db" {
  count = var.deployment_mode == "split_vm" ? 1 : 0

  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.db_instance_type
  subnet_id              = var.private_subnet_id
  vpc_security_group_ids = [var.db_sg_id]
  key_name               = var.key_pair_name
  iam_instance_profile   = var.iam_instance_profile_name

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.db_disk_gb
    encrypted             = true
    delete_on_termination = true

    tags = {
      Name = "${var.prefix}-db-root-vol"
    }
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  user_data = <<-EOF
    #!/bin/bash
    set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive

    apt-get update -y
    apt-get install -y postgresql-16

    # Listen on all interfaces — access controlled by security group
    sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" \
      /etc/postgresql/16/main/postgresql.conf

    # Allow connections from the entire VPC CIDR
    echo "host ${var.db_name} ${var.db_username} ${var.vpc_cidr} scram-sha-256" \
      >> /etc/postgresql/16/main/pg_hba.conf

    # Create database and application user
    sudo -u postgres psql <<SQL
    CREATE USER ${var.db_username} WITH PASSWORD '${var.db_password}';
    CREATE DATABASE ${var.db_name} OWNER ${var.db_username};
    SQL

    systemctl enable postgresql
    systemctl restart postgresql
  EOF

  tags = {
    Name        = "${var.prefix}-db-ec2"
    Environment = var.environment
  }
}

# ── split_managed: RDS PostgreSQL ─────────────────────────────────────────────
# Requires two private subnets in different AZs for the subnet group.

resource "aws_db_subnet_group" "main" {
  count = var.deployment_mode == "split_managed" ? 1 : 0

  name       = "${var.prefix}-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "${var.prefix}-db-subnet-group"
  }
}

resource "aws_db_parameter_group" "main" {
  count = var.deployment_mode == "split_managed" ? 1 : 0

  name   = "${var.prefix}-db-pg16"
  family = "postgres16"

  tags = {
    Name = "${var.prefix}-db-pg16"
  }
}

resource "aws_db_instance" "main" {
  count = var.deployment_mode == "split_managed" ? 1 : 0

  identifier     = "${var.prefix}-rds"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage = var.db_storage_gb
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main[0].name
  parameter_group_name   = aws_db_parameter_group.main[0].name
  vpc_security_group_ids = [var.db_sg_id]

  backup_retention_period = var.db_backup_retention_days
  deletion_protection     = var.db_deletion_protection
  # When deletion_protection is enabled, a final snapshot is taken on destroy.
  # When disabled (dev/test), skip the snapshot to allow clean teardown.
  skip_final_snapshot = !var.db_deletion_protection

  tags = {
    Name        = "${var.prefix}-rds"
    Environment = var.environment
  }
}
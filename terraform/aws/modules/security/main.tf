# ── Application server security group ─────────────────────────────────────────

resource "aws_security_group" "app" {
  name        = "${var.prefix}-app-sg"
  description = "DMARC application server: HTTPS/HTTP open to world, SSH restricted to admin CIDR"
  vpc_id      = var.vpc_id

  tags = {
    Name = "${var.prefix}-app-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  security_group_id = aws_security_group.app.id
  description       = "HTTPS from anywhere"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"

  tags = {
    Name = "${var.prefix}-app-sg-https-in"
  }
}

resource "aws_vpc_security_group_ingress_rule" "http" {
  security_group_id = aws_security_group.app.id
  description       = "HTTP from anywhere (redirect to HTTPS)"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"

  tags = {
    Name = "${var.prefix}-app-sg-http-in"
  }
}

resource "aws_vpc_security_group_ingress_rule" "ssh" {
  security_group_id = aws_security_group.app.id
  description       = "SSH from admin CIDR only"
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_ipv4         = var.admin_cidr

  tags = {
    Name = "${var.prefix}-app-sg-ssh-in"
  }
}

resource "aws_vpc_security_group_ingress_rule" "ssh_cicd" {
  count             = var.cicd_cidr != null ? 1 : 0
  security_group_id = aws_security_group.app.id
  description       = "SSH for CI/CD deployments (self-hosted runner or fixed egress IP)"
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_ipv4         = var.cicd_cidr

  tags = {
    Name = "${var.prefix}-app-sg-ssh-cicd-in"
  }
}

resource "aws_vpc_security_group_egress_rule" "all_outbound" {
  security_group_id = aws_security_group.app.id
  description       = "All outbound traffic"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"

  tags = {
    Name = "${var.prefix}-app-sg-all-out"
  }
}

# ── Database security group (split topologies only) ────────────────────────────
# Allows PostgreSQL only from the app security group — no direct internet access.

resource "aws_security_group" "db" {
  count       = var.create_db_security_group ? 1 : 0
  name        = "${var.prefix}-db-sg"
  description = "Database server: PostgreSQL access from app security group only"
  vpc_id      = var.vpc_id

  tags = {
    Name = "${var.prefix}-db-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "db_postgres" {
  count                        = var.create_db_security_group ? 1 : 0
  security_group_id            = aws_security_group.db[0].id
  description                  = "PostgreSQL from app security group"
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.app.id

  tags = {
    Name = "${var.prefix}-db-sg-pg-in"
  }
}

resource "aws_vpc_security_group_egress_rule" "db_all_outbound" {
  count             = var.create_db_security_group ? 1 : 0
  security_group_id = aws_security_group.db[0].id
  description       = "All outbound traffic (OS updates via NAT Gateway)"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"

  tags = {
    Name = "${var.prefix}-db-sg-all-out"
  }
}
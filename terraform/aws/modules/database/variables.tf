variable "prefix" {
  description = "Resource name prefix in the form {project}-{environment}"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "deployment_mode" {
  description = "standalone | split_vm | split_managed"
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR block — used in pg_hba.conf to allow access from the entire VPC"
  type        = string
}

variable "private_subnet_id" {
  description = "Primary private subnet ID (for split_vm EC2)"
  type        = string
  default     = null
}

variable "private_subnet_ids" {
  description = "All private subnet IDs across both AZs (required for RDS subnet group)"
  type        = list(string)
  default     = []
}

variable "db_sg_id" {
  description = "Database security group ID"
  type        = string
  default     = null
}

variable "key_pair_name" {
  description = "AWS key pair name for SSH access to the DB EC2 (split_vm only)"
  type        = string
  default     = null
}

variable "iam_instance_profile_name" {
  description = "IAM instance profile to attach to the DB EC2 (enables SSM access)"
  type        = string
  default     = null
}

# ── Database sizing ───────────────────────────────────────────────────────────

variable "db_instance_type" {
  description = "EC2 instance type for the DB VM in split_vm mode"
  type        = string
  default     = "t3.small"
}

variable "db_disk_gb" {
  description = "OS disk size for the DB VM in split_vm mode"
  type        = number
  default     = 30
}

variable "db_instance_class" {
  description = "RDS instance class in split_managed mode (e.g. db.t3.micro)"
  type        = string
  default     = "db.t3.micro"
}

variable "db_storage_gb" {
  description = "RDS allocated storage in GB"
  type        = number
  default     = 20
}

# ── Database credentials ──────────────────────────────────────────────────────

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "dmarc"
}

variable "db_username" {
  description = "PostgreSQL superuser username"
  type        = string
  default     = "dmarc"
}

variable "db_password" {
  description = "PostgreSQL superuser password"
  type        = string
  sensitive   = true
}

variable "db_backup_retention_days" {
  description = "Number of days to retain automated RDS backups (split_managed only)"
  type        = number
  default     = 7
}

variable "db_deletion_protection" {
  description = "Enable RDS deletion protection. Recommended true for production."
  type        = bool
  default     = false
}
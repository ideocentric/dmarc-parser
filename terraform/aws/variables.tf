variable "project_name" {
  description = "Project name used as the first segment of all resource names ({project}-{env}-{resource})"
  type        = string
  default     = "dmarc"
}

variable "environment" {
  description = "Deployment environment — second segment of all resource names (prod, staging, dev)"
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "deployment_mode" {
  description = "standalone: app+db on one VM | split_vm: app VM + DB VM in private subnet | split_managed: app VM + RDS PostgreSQL"
  type        = string
  default     = "standalone"

  validation {
    condition     = contains(["standalone", "split_vm", "split_managed"], var.deployment_mode)
    error_message = "deployment_mode must be one of: standalone, split_vm, split_managed."
  }
}

variable "clamav_enabled" {
  description = "Whether ClamAV will run on this instance. Drives automatic instance type selection."
  type        = bool
  default     = true
}

variable "instance_type" {
  description = "EC2 instance type override. Leave null to auto-select based on clamav_enabled (t3.large with ClamAV, t3.medium without)."
  type        = string
  default     = null
}

variable "root_disk_gb" {
  description = "Root EBS volume size in GB for the application server"
  type        = number
  default     = 100
}

variable "admin_cidr" {
  description = "CIDR block allowed SSH access on port 22 (e.g. 203.0.113.5/32)"
  type        = string
}

variable "cicd_cidr" {
  description = "Additional CIDR allowed SSH on port 22 for CI/CD deployments. Null disables the rule."
  type        = string
  default     = null
}

variable "ssh_public_key_path" {
  description = "Path to the local SSH public key file (.pub). Terraform uploads the public key to AWS as a named key pair."
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

# ── Networking ────────────────────────────────────────────────────────────────

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR block for the primary private subnet (DB VM or RDS)"
  type        = string
  default     = "10.0.2.0/24"
}

variable "private_subnet_cidr_2" {
  description = "CIDR block for the second private subnet in a different AZ (required for RDS subnet groups)"
  type        = string
  default     = "10.0.3.0/24"
}

variable "availability_zone" {
  description = "Availability zone for the primary subnet. Defaults to the first AZ in the selected region."
  type        = string
  default     = null
}

# ── Container registry ────────────────────────────────────────────────────────

variable "image_retention_count" {
  description = "Number of tagged container images to retain per ECR repository"
  type        = number
  default     = 10
}

variable "create_ci_user" {
  description = "Create a dedicated IAM user with ECR push and SSM permissions for CI/CD."
  type        = bool
  default     = false
}

# ── Database (split topologies) ───────────────────────────────────────────────

variable "db_password" {
  description = "PostgreSQL password. Required for split_vm and split_managed; unused for standalone."
  type        = string
  sensitive   = true
  default     = ""
}

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

variable "db_instance_type" {
  description = "EC2 instance type for the DB VM (split_vm mode)"
  type        = string
  default     = "t3.small"
}

variable "db_disk_gb" {
  description = "OS disk size in GB for the DB VM (split_vm mode)"
  type        = number
  default     = 30
}

variable "db_instance_class" {
  description = "RDS instance class (split_managed mode, e.g. db.t3.micro)"
  type        = string
  default     = "db.t3.micro"
}

variable "db_storage_gb" {
  description = "RDS allocated storage in GB (split_managed mode)"
  type        = number
  default     = 20
}

variable "db_backup_retention_days" {
  description = "Days to retain automated RDS backups (split_managed mode)"
  type        = number
  default     = 7
}

variable "db_deletion_protection" {
  description = "Enable RDS deletion protection. Recommended true for production."
  type        = bool
  default     = false
}
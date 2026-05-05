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

variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "location" {
  description = "Azure region (e.g. East US, West Europe)"
  type        = string
  default     = "East US"
}

variable "deployment_mode" {
  description = "standalone: app+db on one VM | split_vm: app VM + DB VM in private subnet | split_managed: app VM + Azure PostgreSQL Flexible Server"
  type        = string
  default     = "standalone"

  validation {
    condition     = contains(["standalone", "split_vm", "split_managed"], var.deployment_mode)
    error_message = "deployment_mode must be one of: standalone, split_vm, split_managed."
  }
}

variable "clamav_enabled" {
  description = "Whether ClamAV will run on this instance. Drives automatic VM size selection."
  type        = bool
  default     = true
}

variable "vm_size" {
  description = "Azure VM size override. Leave null to auto-select based on clamav_enabled."
  type        = string
  default     = null
}

variable "root_disk_gb" {
  description = "OS disk size in GB for the application server"
  type        = number
  default     = 100
}

variable "admin_username" {
  description = "OS admin username for SSH login"
  type        = string
  default     = "ubuntu"
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
  description = "Path to the local SSH public key file (.pub)."
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

# ── Networking ────────────────────────────────────────────────────────────────

variable "vnet_cidr" {
  description = "CIDR block for the virtual network"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR block for the private subnet (DB VM in split_vm mode)"
  type        = string
  default     = "10.0.2.0/24"
}

variable "db_subnet_cidr" {
  description = "CIDR block for the delegated PostgreSQL Flexible Server subnet (split_managed only)"
  type        = string
  default     = "10.0.3.0/24"
}

# ── Database (split topologies) ───────────────────────────────────────────────

variable "db_password" {
  description = "PostgreSQL administrator password. Required for split_vm and split_managed."
  type        = string
  sensitive   = true
  default     = ""
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "dmarc"
}

variable "db_admin_username" {
  description = "PostgreSQL administrator username"
  type        = string
  default     = "dmarc_admin"
}

variable "db_vm_size" {
  description = "Azure VM size for the DB VM (split_vm mode)"
  type        = string
  default     = "Standard_B2s"
}

variable "db_disk_gb" {
  description = "OS disk size in GB for the DB VM (split_vm mode)"
  type        = number
  default     = 30
}

variable "db_sku_name" {
  description = "Azure PostgreSQL Flexible Server compute SKU (split_managed mode)"
  type        = string
  default     = "B_Standard_B1ms"
}

variable "db_storage_mb" {
  description = "Storage size for PostgreSQL Flexible Server in MB (split_managed mode, min 32768)"
  type        = number
  default     = 32768
}

variable "db_version" {
  description = "PostgreSQL major version"
  type        = string
  default     = "16"
}

variable "db_backup_retention_days" {
  description = "Days to retain automated database backups (split_managed mode)"
  type        = number
  default     = 7
}
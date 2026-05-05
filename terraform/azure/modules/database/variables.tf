variable "prefix" {
  description = "Resource name prefix in the form {project}-{environment}"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the Azure resource group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "deployment_mode" {
  description = "standalone | split_vm | split_managed"
  type        = string
}

variable "vnet_id" {
  description = "VNet ID — used for PostgreSQL Flexible Server private DNS zone link"
  type        = string
}

variable "vnet_cidr" {
  description = "VNet CIDR block — used in pg_hba.conf to allow connections from the VNet"
  type        = string
}

variable "private_subnet_id" {
  description = "Private subnet ID for the DB VM NIC (split_vm only)"
  type        = string
  default     = null
}

variable "db_delegated_subnet_id" {
  description = "Delegated subnet ID for PostgreSQL Flexible Server (split_managed only)"
  type        = string
  default     = null
}

# ── DB VM sizing (split_vm) ───────────────────────────────────────────────────

variable "db_vm_size" {
  description = "Azure VM size for the database VM (split_vm mode)"
  type        = string
  default     = "Standard_B2s"
}

variable "db_disk_gb" {
  description = "OS disk size for the DB VM in GB"
  type        = number
  default     = 30
}

variable "admin_username" {
  description = "OS admin username"
  type        = string
  default     = "ubuntu"
}

variable "ssh_public_key_path" {
  description = "Path to the local SSH public key file"
  type        = string
}

# ── Managed DB sizing (split_managed) ────────────────────────────────────────

variable "db_sku_name" {
  description = "Azure PostgreSQL Flexible Server SKU (e.g. B_Standard_B1ms)"
  type        = string
  default     = "B_Standard_B1ms"
}

variable "db_storage_mb" {
  description = "Storage size for PostgreSQL Flexible Server in MB (min 32768)"
  type        = number
  default     = 32768
}

variable "db_version" {
  description = "PostgreSQL major version"
  type        = string
  default     = "16"
}

# ── Database credentials ──────────────────────────────────────────────────────

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

variable "db_password" {
  description = "PostgreSQL administrator password"
  type        = string
  sensitive   = true
}

variable "db_backup_retention_days" {
  description = "Number of days to retain automated backups (split_managed only)"
  type        = number
  default     = 7
}
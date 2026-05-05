variable "prefix" {
  description = "Resource name prefix in the form {project}-{environment}"
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

variable "public_subnet_id" {
  description = "Public subnet ID to associate the app NSG with"
  type        = string
}

variable "private_subnet_id" {
  description = "Private subnet ID to associate the DB NSG with (null for standalone)"
  type        = string
  default     = null
}

variable "vnet_address_space" {
  description = "VNet address space — used as the source prefix in the DB NSG PostgreSQL rule"
  type        = string
}

variable "admin_cidr" {
  description = "CIDR allowed SSH access on port 22"
  type        = string
}

variable "cicd_cidr" {
  description = "Additional CIDR allowed SSH on port 22 for CI/CD. Null disables the rule."
  type        = string
  default     = null
}

variable "create_db_security_group" {
  description = "Create a DB NSG for the private subnet. True for split topologies."
  type        = bool
  default     = false
}
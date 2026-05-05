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
  description = "Public subnet ID to associate the NSG with"
  type        = string
}

variable "admin_cidr" {
  description = "CIDR allowed SSH access on port 22 (e.g. 203.0.113.5/32)"
  type        = string
}

variable "cicd_cidr" {
  description = "Additional CIDR allowed SSH on port 22 for CI/CD. Null disables the rule."
  type        = string
  default     = null
}
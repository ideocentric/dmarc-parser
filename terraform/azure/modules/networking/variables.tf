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

variable "vnet_cidr" {
  description = "CIDR block for the virtual network"
  type        = string
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet"
  type        = string
}

variable "private_subnet_cidr" {
  description = "CIDR block for the private subnet (used by DB VM in split_vm mode)"
  type        = string
  default     = "10.0.2.0/24"
}

variable "db_subnet_cidr" {
  description = "CIDR block for the delegated PostgreSQL subnet (split_managed only)"
  type        = string
  default     = "10.0.3.0/24"
}

variable "create_private_network" {
  description = "Create private subnet and NAT Gateway. True for split_vm and split_managed."
  type        = bool
  default     = false
}

variable "create_db_delegated_subnet" {
  description = "Create a delegated subnet for Azure PostgreSQL Flexible Server (split_managed only)."
  type        = bool
  default     = false
}
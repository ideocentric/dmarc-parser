variable "prefix" {
  description = "Resource name prefix in the form {project}-{environment}"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the Azure resource group to deploy into"
  type        = string
}

variable "location" {
  description = "Azure region (e.g. East US)"
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
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

variable "acr_id" {
  description = "ACR resource ID to scope the AcrPull role assignment"
  type        = string
}
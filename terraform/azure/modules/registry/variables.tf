variable "acr_name" {
  description = "Azure Container Registry name — must be globally unique, 5-50 alphanumeric characters (no hyphens)"
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
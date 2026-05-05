variable "prefix" {
  description = "Resource name prefix in the form {project}-{environment}"
  type        = string
}

variable "environment" {
  description = "Deployment environment — included in VM tags for console clarity"
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

variable "subnet_id" {
  description = "Subnet ID to attach the network interface to"
  type        = string
}

variable "vm_size" {
  description = "Azure VM size (e.g. Standard_B2ms)"
  type        = string
}

variable "root_disk_gb" {
  description = "OS disk size in GB"
  type        = number
  default     = 100
}

variable "admin_username" {
  description = "OS admin username for SSH login"
  type        = string
  default     = "ubuntu"
}

variable "ssh_public_key_path" {
  description = "Path to the local SSH public key file (.pub). The private key stays on your machine."
  type        = string
}

variable "managed_identity_id" {
  description = "Resource ID of the user-assigned managed identity to attach to the VM (enables ACR pull)"
  type        = string
}
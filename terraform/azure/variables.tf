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
  description = "Topology: standalone (app+db on one VM) | split_vm | split_managed"
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
  description = "Azure VM size override. Leave null to auto-select based on clamav_enabled (Standard_B2ms with ClamAV, Standard_B2s without)."
  type        = string
  default     = null
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
  description = "Path to the local SSH public key file (.pub). The private key stays on your machine."
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

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
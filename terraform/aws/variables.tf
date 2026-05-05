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

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
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
  description = "Whether ClamAV will run on this instance. Drives automatic instance type selection."
  type        = bool
  default     = true
}

variable "instance_type" {
  description = "EC2 instance type override. Leave null to auto-select based on clamav_enabled (t3.large with ClamAV, t3.medium without)."
  type        = string
  default     = null
}

variable "root_disk_gb" {
  description = "Root EBS volume size in GB"
  type        = number
  default     = 100
}

variable "admin_cidr" {
  description = "CIDR block allowed SSH access on port 22 (e.g. 203.0.113.5/32 for a single IP)"
  type        = string
}

variable "cicd_cidr" {
  description = "Additional CIDR allowed SSH on port 22 for CI/CD deployments. Use a fixed egress IP for a self-hosted runner, or 0.0.0.0/0 for GitHub-hosted runners. Null disables the rule."
  type        = string
  default     = null
}

variable "ssh_public_key_path" {
  description = "Path to the local SSH public key file (.pub). Terraform uploads the public key to AWS as a named key pair; the private key stays on your machine."
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "availability_zone" {
  description = "Availability zone for the public subnet. Defaults to the first AZ in the selected region."
  type        = string
  default     = null
}

variable "image_retention_count" {
  description = "Number of tagged container images to retain per ECR repository"
  type        = number
  default     = 10
}

variable "create_ci_user" {
  description = "Create a dedicated IAM user with ECR push and SSM permissions for CI/CD. Set false when using GitHub Actions OIDC instead."
  type        = bool
  default     = false
}
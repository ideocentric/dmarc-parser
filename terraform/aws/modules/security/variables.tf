variable "prefix" {
  description = "Resource name prefix in the form {project}-{environment}"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID to create the security group in"
  type        = string
}

variable "admin_cidr" {
  description = "CIDR allowed SSH access on port 22 (e.g. your office IP as 203.0.113.5/32)"
  type        = string
}

variable "cicd_cidr" {
  description = "Additional CIDR allowed SSH on port 22 for CI/CD deployments. Set to null to disable. Use a fixed egress IP (self-hosted runner) or 0.0.0.0/0 for GitHub-hosted runners (less secure)."
  type        = string
  default     = null
}
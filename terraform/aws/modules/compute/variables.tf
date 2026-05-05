variable "prefix" {
  description = "Resource name prefix in the form {project}-{environment}"
  type        = string
}

variable "environment" {
  description = "Deployment environment — included in instance tags for console clarity"
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID to launch the instance in"
  type        = string
}

variable "security_group_id" {
  description = "Security group ID to attach to the instance"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
}

variable "root_disk_gb" {
  description = "Root EBS volume size in GB"
  type        = number
  default     = 100
}

variable "ssh_public_key_path" {
  description = "Path to local SSH public key file (.pub). Terraform uploads the public key to AWS as {prefix}-keypair; the private key stays on your machine."
  type        = string
}

variable "iam_instance_profile_name" {
  description = "IAM instance profile to attach to the EC2 instance (enables ECR pull and SSM access)"
  type        = string
}
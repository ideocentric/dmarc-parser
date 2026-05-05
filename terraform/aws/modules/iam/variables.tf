variable "prefix" {
  description = "Resource name prefix in the form {project}-{environment}"
  type        = string
}

variable "ecr_repository_arns" {
  description = "ARNs of the ECR repositories the CI user may push to"
  type        = list(string)
  default     = []
}

variable "create_ci_user" {
  description = "Create a dedicated IAM user for CI/CD ECR push access. Set true if not using OIDC."
  type        = bool
  default     = false
}
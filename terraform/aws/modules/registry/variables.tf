variable "prefix" {
  description = "Resource name prefix in the form {project}-{environment}"
  type        = string
}

variable "image_retention_count" {
  description = "Number of tagged images to retain per repository. Older images are expired automatically."
  type        = number
  default     = 10
}
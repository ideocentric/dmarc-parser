variable "prefix" {
  description = "Resource name prefix in the form {project}-{environment}"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet"
  type        = string
}

variable "private_subnet_cidr" {
  description = "CIDR block for private subnet 1 (used by DB VM in split_vm mode)"
  type        = string
  default     = "10.0.2.0/24"
}

variable "private_subnet_cidr_2" {
  description = "CIDR block for private subnet 2 (second AZ — required for RDS subnet groups in split_managed mode)"
  type        = string
  default     = "10.0.3.0/24"
}

variable "create_private_network" {
  description = "Create private subnets and NAT Gateway. True for split_vm and split_managed; false for standalone."
  type        = bool
  default     = false
}

variable "availability_zone" {
  description = "AZ for the primary subnet. Null defaults to the first available AZ in the region."
  type        = string
  default     = null
}
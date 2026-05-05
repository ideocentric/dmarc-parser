variable "prefix" {
  type = string
}

variable "environment" {
  type = string
}

variable "region" {
  type = string
}

variable "instance_type" {
  type = string
}

variable "ssh_public_key" {
  type      = string
  sensitive = true
}

variable "firewall_id" {
  type = number
}

variable "vpc_subnet_id" {
  type    = number
  default = null
}

variable "create_vpc_iface" {
  type = bool
}
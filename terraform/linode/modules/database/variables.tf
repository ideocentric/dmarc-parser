variable "prefix" {
  type = string
}

variable "environment" {
  type = string
}

variable "region" {
  type = string
}

variable "deployment_mode" {
  type = string
}

# ── split_vm ──────────────────────────────────────────────────────────────────

variable "ssh_public_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "db_firewall_id" {
  type    = number
  default = null
}

variable "vpc_subnet_id" {
  type    = number
  default = null
}

variable "db_instance_type" {
  type    = string
  default = "g6-standard-1"
}

# ── split_managed ─────────────────────────────────────────────────────────────

variable "db_cluster_size" {
  type    = number
  default = 1
}

variable "db_engine" {
  type    = string
  default = "postgresql/16"
}

variable "app_public_ip" {
  type    = string
  default = ""
}

# ── shared ────────────────────────────────────────────────────────────────────

variable "db_name" {
  type    = string
  default = "dmarc"
}

variable "db_username" {
  type    = string
  default = "dmarc"
}

variable "db_password" {
  type      = string
  sensitive = true
  default   = ""
}
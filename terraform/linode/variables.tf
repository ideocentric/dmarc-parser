variable "project_name" {
  description = "Project name — first segment of all resource labels ({project}-{env}-{resource})"
  type        = string
  default     = "dmarc"
}

variable "environment" {
  description = "Deployment environment — second segment of all resource labels (prod, staging, dev)"
  type        = string
  default     = "prod"
}

variable "linode_token" {
  description = "Linode API personal access token. Sensitive — use LINODE_TOKEN env var or terraform.tfvars, never commit."
  type        = string
  sensitive   = true
}

variable "region" {
  description = "Linode region slug (e.g. us-east, eu-west, ap-southeast). Run: linode-cli regions list"
  type        = string
  default     = "us-east"
}

variable "deployment_mode" {
  description = "standalone: app+db on one Linode | split_vm: app + DB Linode over VPC | split_managed: app Linode + Linode Managed PostgreSQL"
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
  description = "Linode instance type override. Null auto-selects: g6-standard-4 with ClamAV, g6-standard-2 without."
  type        = string
  default     = null
}

variable "admin_cidr" {
  description = "CIDR allowed SSH access on port 22 (e.g. 203.0.113.5/32). Find your IP: curl -s https://checkip.amazonaws.com"
  type        = string
}

variable "ssh_public_key_path" {
  description = "Path to the local SSH public key file (.pub). The public key is uploaded to the Linode as an authorised key."
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

# ── Networking ────────────────────────────────────────────────────────────────

variable "vpc_subnet_cidr" {
  description = "IPv4 CIDR for the private VPC subnet used in split topologies"
  type        = string
  default     = "10.8.0.0/24"
}

# ── Database (split topologies) ───────────────────────────────────────────────

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "dmarc"
}

variable "db_username" {
  description = "PostgreSQL superuser username"
  type        = string
  default     = "dmarc"
}

variable "db_password" {
  description = "PostgreSQL password for split_vm mode. Not used for split_managed (Linode auto-generates the password — retrieve with: terraform output -raw db_password)."
  type        = string
  sensitive   = true
  default     = ""
}

variable "db_instance_type" {
  description = "Linode instance type for the DB VM (split_vm mode). g6-standard-1 = 2 GB RAM."
  type        = string
  default     = "g6-standard-1"
}

variable "db_cluster_size" {
  description = "Node count for Linode Managed PostgreSQL (split_managed). 1 = single, 2 = primary+standby, 3 = HA"
  type        = number
  default     = 1
}

variable "db_engine" {
  description = "Engine ID for Linode Managed PostgreSQL (split_managed). Run: linode-cli databases engines-list"
  type        = string
  default     = "postgresql/16"
}
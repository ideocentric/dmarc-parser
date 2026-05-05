terraform {
  required_version = ">= 1.5"

  required_providers {
    linode = {
      source  = "linode/linode"
      version = "~> 2.0"
    }
  }
}

provider "linode" {
  token = var.linode_token
}

locals {
  prefix = "${var.project_name}-${var.environment}"

  # g6-standard-4 (4 CPU / 8 GB RAM) when ClamAV is enabled — the daemon
  # loads ~700 MB–1 GB of signatures at startup, which overwhelms a 4 GB node.
  # g6-standard-2 (2 CPU / 4 GB RAM) is adequate without ClamAV.
  default_instance_type = var.clamav_enabled ? "g6-standard-4" : "g6-standard-2"
  instance_type         = coalesce(var.instance_type, local.default_instance_type)

  create_private_network = var.deployment_mode != "standalone"
}

module "networking" {
  source = "./modules/networking"

  prefix                 = local.prefix
  region                 = var.region
  vpc_subnet_cidr        = var.vpc_subnet_cidr
  create_private_network = local.create_private_network
}

module "firewall" {
  source = "./modules/firewall"

  prefix          = local.prefix
  admin_cidr      = var.admin_cidr
  vpc_subnet_cidr = var.vpc_subnet_cidr
  deployment_mode = var.deployment_mode
}

module "compute" {
  source = "./modules/compute"

  prefix           = local.prefix
  environment      = var.environment
  region           = var.region
  instance_type    = local.instance_type
  ssh_public_key   = file(pathexpand(var.ssh_public_key_path))
  firewall_id      = module.firewall.app_firewall_id
  vpc_subnet_id    = module.networking.vpc_subnet_id
  create_vpc_iface = local.create_private_network
}

module "database" {
  source = "./modules/database"

  prefix          = local.prefix
  environment     = var.environment
  region          = var.region
  deployment_mode = var.deployment_mode

  # split_vm
  ssh_public_key   = file(pathexpand(var.ssh_public_key_path))
  db_firewall_id   = module.firewall.db_firewall_id
  vpc_subnet_id    = module.networking.vpc_subnet_id
  db_instance_type = var.db_instance_type

  # split_managed
  db_cluster_size = var.db_cluster_size
  db_engine       = var.db_engine
  app_public_ip   = module.compute.public_ip

  # shared
  db_name     = var.db_name
  db_username = var.db_username
  db_password = var.db_password
}
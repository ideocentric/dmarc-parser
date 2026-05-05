terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

locals {
  prefix = "${var.project_name}-${var.environment}"

  # t3.large (2 vCPU / 8 GB) when ClamAV is enabled — the daemon loads ~700 MB–1 GB of
  # virus signatures into RAM at startup, which pushes a t3.medium too close to its limit.
  default_instance_type = var.clamav_enabled ? "t3.large" : "t3.medium"
  instance_type         = coalesce(var.instance_type, local.default_instance_type)

  # Derived from deployment_mode — drives private network and DB security group creation
  create_private_network   = var.deployment_mode != "standalone"
  create_db_security_group = var.deployment_mode != "standalone"
}

module "networking" {
  source = "./modules/networking"

  prefix                 = local.prefix
  vpc_cidr               = var.vpc_cidr
  public_subnet_cidr     = var.public_subnet_cidr
  private_subnet_cidr    = var.private_subnet_cidr
  private_subnet_cidr_2  = var.private_subnet_cidr_2
  create_private_network = local.create_private_network
  availability_zone      = var.availability_zone
}

module "security" {
  source = "./modules/security"

  prefix                   = local.prefix
  vpc_id                   = module.networking.vpc_id
  admin_cidr               = var.admin_cidr
  cicd_cidr                = var.cicd_cidr
  create_db_security_group = local.create_db_security_group
}

module "registry" {
  source = "./modules/registry"

  prefix                = local.prefix
  image_retention_count = var.image_retention_count
}

module "iam" {
  source = "./modules/iam"

  prefix              = local.prefix
  create_ci_user      = var.create_ci_user
  ecr_repository_arns = [module.registry.api_repo_url, module.registry.frontend_repo_url]
}

module "compute" {
  source = "./modules/compute"

  prefix                    = local.prefix
  environment               = var.environment
  subnet_id                 = module.networking.public_subnet_id
  security_group_id         = module.security.app_sg_id
  instance_type             = local.instance_type
  root_disk_gb              = var.root_disk_gb
  ssh_public_key_path       = var.ssh_public_key_path
  iam_instance_profile_name = module.iam.instance_profile_name
}

module "database" {
  source = "./modules/database"

  prefix          = local.prefix
  environment     = var.environment
  deployment_mode = var.deployment_mode
  vpc_cidr        = var.vpc_cidr

  private_subnet_id  = module.networking.private_subnet_id
  private_subnet_ids = module.networking.private_subnet_ids
  db_sg_id           = module.security.db_sg_id

  # The DB EC2 (split_vm) uses the same key pair as the app server
  key_pair_name             = module.compute.key_pair_name
  iam_instance_profile_name = module.iam.instance_profile_name

  db_instance_type         = var.db_instance_type
  db_disk_gb               = var.db_disk_gb
  db_instance_class        = var.db_instance_class
  db_storage_gb            = var.db_storage_gb
  db_name                  = var.db_name
  db_username              = var.db_username
  db_password              = var.db_password
  db_backup_retention_days = var.db_backup_retention_days
  db_deletion_protection   = var.db_deletion_protection
}
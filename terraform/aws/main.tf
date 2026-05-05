terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.43"
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
}

module "networking" {
  source = "./modules/networking"

  prefix             = local.prefix
  vpc_cidr           = var.vpc_cidr
  public_subnet_cidr = var.public_subnet_cidr
  availability_zone  = var.availability_zone
}

module "security" {
  source = "./modules/security"

  prefix     = local.prefix
  vpc_id     = module.networking.vpc_id
  admin_cidr = var.admin_cidr
  cicd_cidr  = var.cicd_cidr
}

module "registry" {
  source = "./modules/registry"

  prefix                = local.prefix
  image_retention_count = var.image_retention_count
}

module "iam" {
  source = "./modules/iam"

  prefix               = local.prefix
  create_ci_user       = var.create_ci_user
  ecr_repository_arns  = [module.registry.api_repo_url, module.registry.frontend_repo_url]
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
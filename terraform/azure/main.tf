terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

locals {
  prefix = "${var.project_name}-${var.environment}"

  # Standard_B2ms (2 vCPU / 8 GB) when ClamAV is enabled.
  default_vm_size = var.clamav_enabled ? "Standard_B2ms" : "Standard_B2s"
  vm_size         = coalesce(var.vm_size, local.default_vm_size)

  # ACR names must be globally unique and alphanumeric only (no hyphens)
  acr_name = "${replace(local.prefix, "-", "")}acr"

  # Derived from deployment_mode
  create_private_network     = var.deployment_mode != "standalone"
  create_db_security_group   = var.deployment_mode != "standalone"
  create_db_delegated_subnet = var.deployment_mode == "split_managed"
}

resource "azurerm_resource_group" "main" {
  name     = "${local.prefix}-rg"
  location = var.location

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

module "networking" {
  source = "./modules/networking"

  prefix                     = local.prefix
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  vnet_cidr                  = var.vnet_cidr
  public_subnet_cidr         = var.public_subnet_cidr
  private_subnet_cidr        = var.private_subnet_cidr
  db_subnet_cidr             = var.db_subnet_cidr
  create_private_network     = local.create_private_network
  create_db_delegated_subnet = local.create_db_delegated_subnet
}

module "security" {
  source = "./modules/security"

  prefix                   = local.prefix
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  public_subnet_id         = module.networking.public_subnet_id
  private_subnet_id        = module.networking.private_subnet_id
  vnet_address_space       = module.networking.vnet_address_space
  admin_cidr               = var.admin_cidr
  cicd_cidr                = var.cicd_cidr
  create_db_security_group = local.create_db_security_group
}

module "registry" {
  source = "./modules/registry"

  acr_name            = local.acr_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
}

module "iam" {
  source = "./modules/iam"

  prefix              = local.prefix
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  acr_id              = module.registry.acr_id
}

module "compute" {
  source = "./modules/compute"

  prefix              = local.prefix
  environment         = var.environment
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  subnet_id           = module.networking.public_subnet_id
  vm_size             = local.vm_size
  root_disk_gb        = var.root_disk_gb
  admin_username      = var.admin_username
  ssh_public_key_path = var.ssh_public_key_path
  managed_identity_id = module.iam.managed_identity_id
}

module "database" {
  source = "./modules/database"

  prefix              = local.prefix
  environment         = var.environment
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  deployment_mode     = var.deployment_mode
  vnet_id             = module.networking.vnet_id
  vnet_cidr           = var.vnet_cidr

  private_subnet_id      = module.networking.private_subnet_id
  db_delegated_subnet_id = module.networking.db_delegated_subnet_id

  db_vm_size          = var.db_vm_size
  db_disk_gb          = var.db_disk_gb
  admin_username      = var.admin_username
  ssh_public_key_path = var.ssh_public_key_path

  db_sku_name              = var.db_sku_name
  db_storage_mb            = var.db_storage_mb
  db_version               = var.db_version
  db_name                  = var.db_name
  db_admin_username        = var.db_admin_username
  db_password              = var.db_password
  db_backup_retention_days = var.db_backup_retention_days
}
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

  # Standard_B2ms (2 vCPU / 8 GB) when ClamAV is enabled — virus signatures need ~700 MB–1 GB RAM.
  # Standard_B2s (2 vCPU / 4 GB) is sufficient without ClamAV.
  default_vm_size = var.clamav_enabled ? "Standard_B2ms" : "Standard_B2s"
  vm_size         = coalesce(var.vm_size, local.default_vm_size)

  # ACR names must be globally unique and alphanumeric only (no hyphens)
  acr_name = "${replace(local.prefix, "-", "")}acr"
}

# All resources for this deployment live in one resource group
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

  prefix              = local.prefix
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  vnet_cidr           = var.vnet_cidr
  public_subnet_cidr  = var.public_subnet_cidr
}

module "security" {
  source = "./modules/security"

  prefix              = local.prefix
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  public_subnet_id    = module.networking.public_subnet_id
  admin_cidr          = var.admin_cidr
  cicd_cidr           = var.cicd_cidr
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
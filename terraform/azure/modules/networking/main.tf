resource "azurerm_virtual_network" "main" {
  name                = "${var.prefix}-vnet"
  address_space       = [var.vnet_cidr]
  location            = var.location
  resource_group_name = var.resource_group_name

  tags = {
    Name = "${var.prefix}-vnet"
  }
}

resource "azurerm_subnet" "public" {
  name                 = "${var.prefix}-public-snet"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.public_subnet_cidr]
}
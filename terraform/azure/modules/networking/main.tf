resource "azurerm_virtual_network" "main" {
  name                = "${var.prefix}-vnet"
  address_space       = [var.vnet_cidr]
  location            = var.location
  resource_group_name = var.resource_group_name

  tags = {
    Name = "${var.prefix}-vnet"
  }
}

# ── Public subnet ─────────────────────────────────────────────────────────────

resource "azurerm_subnet" "public" {
  name                 = "${var.prefix}-public-snet"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.public_subnet_cidr]
}

# ── Private subnet (split_vm DB) ──────────────────────────────────────────────

resource "azurerm_subnet" "private" {
  count                = var.create_private_network ? 1 : 0
  name                 = "${var.prefix}-private-snet"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.private_subnet_cidr]
}

# ── Delegated subnet (split_managed PostgreSQL Flexible Server) ────────────────
# Azure PostgreSQL Flexible Server requires an exclusively delegated subnet.

resource "azurerm_subnet" "db_delegated" {
  count                = var.create_db_delegated_subnet ? 1 : 0
  name                 = "${var.prefix}-db-snet"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.db_subnet_cidr]

  delegation {
    name = "postgresql-delegation"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

# ── NAT Gateway (private subnet outbound connectivity) ────────────────────────

resource "azurerm_public_ip" "nat" {
  count               = var.create_private_network ? 1 : 0
  name                = "${var.prefix}-nat-pip"
  resource_group_name = var.resource_group_name
  location            = var.location
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = {
    Name = "${var.prefix}-nat-pip"
  }
}

resource "azurerm_nat_gateway" "main" {
  count               = var.create_private_network ? 1 : 0
  name                = "${var.prefix}-nat-gw"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku_name            = "Standard"

  tags = {
    Name = "${var.prefix}-nat-gw"
  }
}

resource "azurerm_nat_gateway_public_ip_association" "main" {
  count                = var.create_private_network ? 1 : 0
  nat_gateway_id       = azurerm_nat_gateway.main[0].id
  public_ip_address_id = azurerm_public_ip.nat[0].id
}

resource "azurerm_subnet_nat_gateway_association" "private" {
  count          = var.create_private_network ? 1 : 0
  subnet_id      = azurerm_subnet.private[0].id
  nat_gateway_id = azurerm_nat_gateway.main[0].id
}
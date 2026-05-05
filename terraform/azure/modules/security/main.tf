resource "azurerm_network_security_group" "app" {
  name                = "${var.prefix}-app-nsg"
  location            = var.location
  resource_group_name = var.resource_group_name

  tags = {
    Name = "${var.prefix}-app-nsg"
  }
}

resource "azurerm_network_security_rule" "https" {
  name                        = "${var.prefix}-allow-https"
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "*"
  destination_address_prefix  = "*"
  description                 = "HTTPS from anywhere"
  resource_group_name         = var.resource_group_name
  network_security_group_name = azurerm_network_security_group.app.name
}

resource "azurerm_network_security_rule" "http" {
  name                        = "${var.prefix}-allow-http"
  priority                    = 110
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "80"
  source_address_prefix       = "*"
  destination_address_prefix  = "*"
  description                 = "HTTP from anywhere (ACME challenge + redirect to HTTPS)"
  resource_group_name         = var.resource_group_name
  network_security_group_name = azurerm_network_security_group.app.name
}

resource "azurerm_network_security_rule" "ssh_admin" {
  name                        = "${var.prefix}-allow-ssh-admin"
  priority                    = 120
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = var.admin_cidr
  destination_address_prefix  = "*"
  description                 = "SSH from admin CIDR only"
  resource_group_name         = var.resource_group_name
  network_security_group_name = azurerm_network_security_group.app.name
}

resource "azurerm_network_security_rule" "ssh_cicd" {
  count = var.cicd_cidr != null ? 1 : 0

  name                        = "${var.prefix}-allow-ssh-cicd"
  priority                    = 130
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = var.cicd_cidr
  destination_address_prefix  = "*"
  description                 = "SSH for CI/CD deployments"
  resource_group_name         = var.resource_group_name
  network_security_group_name = azurerm_network_security_group.app.name
}

# Associate NSG with the public subnet — rules apply to all resources in the subnet
resource "azurerm_subnet_network_security_group_association" "public" {
  subnet_id                 = var.public_subnet_id
  network_security_group_id = azurerm_network_security_group.app.id
}
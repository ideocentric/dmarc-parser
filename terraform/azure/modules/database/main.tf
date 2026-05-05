# ── split_vm: PostgreSQL on a VM in the private subnet ───────────────────────

resource "azurerm_network_interface" "db" {
  count               = var.deployment_mode == "split_vm" ? 1 : 0
  name                = "${var.prefix}-db-nic"
  resource_group_name = var.resource_group_name
  location            = var.location

  ip_configuration {
    name                          = "internal"
    subnet_id                     = var.private_subnet_id
    private_ip_address_allocation = "Dynamic"
    # No public IP — reachable only from within the VNet
  }

  tags = {
    Name = "${var.prefix}-db-nic"
  }
}

resource "azurerm_linux_virtual_machine" "db" {
  count                 = var.deployment_mode == "split_vm" ? 1 : 0
  name                  = "${var.prefix}-db-vm"
  computer_name         = "${var.prefix}-db-vm"
  resource_group_name   = var.resource_group_name
  location              = var.location
  size                  = var.db_vm_size
  admin_username        = var.admin_username
  network_interface_ids = [azurerm_network_interface.db[0].id]

  disable_password_authentication = true

  admin_ssh_key {
    username   = var.admin_username
    public_key = file(pathexpand(var.ssh_public_key_path))
  }

  os_disk {
    name                 = "${var.prefix}-db-os-disk"
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = var.db_disk_gb
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  custom_data = base64encode(<<-EOF
    #!/bin/bash
    set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive

    apt-get update -y
    apt-get install -y postgresql-16

    # Listen on all interfaces — access restricted by NSG
    sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" \
      /etc/postgresql/16/main/postgresql.conf

    # Allow connections from the entire VNet CIDR
    echo "host ${var.db_name} ${var.db_admin_username} ${var.vnet_cidr} scram-sha-256" \
      >> /etc/postgresql/16/main/pg_hba.conf

    # Create database and application user
    sudo -u postgres psql <<SQL
    CREATE USER ${var.db_admin_username} WITH PASSWORD '${var.db_password}';
    CREATE DATABASE ${var.db_name} OWNER ${var.db_admin_username};
    SQL

    systemctl enable postgresql
    systemctl restart postgresql
  EOF
  )

  tags = {
    Name        = "${var.prefix}-db-vm"
    Environment = var.environment
  }
}

# ── split_managed: Azure Database for PostgreSQL Flexible Server ──────────────
# Deployed into the delegated subnet with VNet integration.
# A private DNS zone resolves the server FQDN within the VNet.

resource "azurerm_private_dns_zone" "postgres" {
  count               = var.deployment_mode == "split_managed" ? 1 : 0
  name                = "${var.prefix}.postgres.database.azure.com"
  resource_group_name = var.resource_group_name

  tags = {
    Name = "${var.prefix}-postgres-dns"
  }
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  count                 = var.deployment_mode == "split_managed" ? 1 : 0
  name                  = "${var.prefix}-postgres-dns-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.postgres[0].name
  virtual_network_id    = var.vnet_id

  tags = {
    Name = "${var.prefix}-postgres-dns-link"
  }
}

resource "azurerm_postgresql_flexible_server" "main" {
  count               = var.deployment_mode == "split_managed" ? 1 : 0
  name                = "${var.prefix}-pgsql"
  resource_group_name = var.resource_group_name
  location            = var.location
  version             = var.db_version

  delegated_subnet_id = var.db_delegated_subnet_id
  private_dns_zone_id = azurerm_private_dns_zone.postgres[0].id

  administrator_login    = var.db_admin_username
  administrator_password = var.db_password

  sku_name   = var.db_sku_name
  storage_mb = var.db_storage_mb

  backup_retention_days        = var.db_backup_retention_days
  geo_redundant_backup_enabled = false

  tags = {
    Name        = "${var.prefix}-pgsql"
    Environment = var.environment
  }

  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]
}

resource "azurerm_postgresql_flexible_server_database" "main" {
  count     = var.deployment_mode == "split_managed" ? 1 : 0
  name      = var.db_name
  server_id = azurerm_postgresql_flexible_server.main[0].id
  collation = "en_US.utf8"
  charset   = "utf8"
}
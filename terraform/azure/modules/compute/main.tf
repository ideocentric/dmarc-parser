# Reserved static public IP — persists across VM stop/start cycles
resource "azurerm_public_ip" "app" {
  name                = "${var.prefix}-pip"
  resource_group_name = var.resource_group_name
  location            = var.location
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = {
    Name = "${var.prefix}-pip"
  }
}

resource "azurerm_network_interface" "app" {
  name                = "${var.prefix}-nic"
  resource_group_name = var.resource_group_name
  location            = var.location

  ip_configuration {
    name                          = "internal"
    subnet_id                     = var.subnet_id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.app.id
  }

  tags = {
    Name = "${var.prefix}-nic"
  }
}

resource "azurerm_linux_virtual_machine" "app" {
  name                  = "${var.prefix}-vm"
  computer_name         = "${var.prefix}-vm"
  resource_group_name   = var.resource_group_name
  location              = var.location
  size                  = var.vm_size
  admin_username        = var.admin_username
  network_interface_ids = [azurerm_network_interface.app.id]

  disable_password_authentication = true

  admin_ssh_key {
    username   = var.admin_username
    public_key = file(pathexpand(var.ssh_public_key_path))
  }

  os_disk {
    name                 = "${var.prefix}-os-disk"
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = var.root_disk_gb
  }

  # Latest Ubuntu 24.04 LTS (Noble Numbat) from Canonical
  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  # User-assigned managed identity — allows ACR pull and Azure CLI auth without stored credentials
  identity {
    type         = "UserAssigned"
    identity_ids = [var.managed_identity_id]
  }

  custom_data = base64encode(<<-EOF
    #!/bin/bash
    set -euo pipefail

    # System update
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get upgrade -y

    # Docker prerequisites
    apt-get install -y ca-certificates curl gnupg

    # Docker GPG key and repository
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      | tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Install Docker Engine + Compose plugin
    apt-get update -y
    apt-get install -y \
      docker-ce \
      docker-ce-cli \
      containerd.io \
      docker-buildx-plugin \
      docker-compose-plugin

    # Allow ${var.admin_username} to run docker without sudo
    usermod -aG docker ${var.admin_username}

    # Enable Docker on boot
    systemctl enable docker
    systemctl start docker

    # Azure CLI — required for managed identity ACR authentication on the VM
    curl -sL https://aka.ms/InstallAzureCLIDeb | bash

    # Application directory
    mkdir -p /opt/dmarc
    chown ${var.admin_username}:${var.admin_username} /opt/dmarc
  EOF
  )

  tags = {
    Name        = "${var.prefix}-vm"
    Environment = var.environment
  }
}
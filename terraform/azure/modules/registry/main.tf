resource "azurerm_container_registry" "main" {
  name                = var.acr_name
  resource_group_name = var.resource_group_name
  location            = var.location

  # Standard SKU supports vulnerability scanning and geo-replication (if needed later)
  sku = "Standard"

  # Managed identity handles all auth — admin credentials not required
  admin_enabled = false

  tags = {
    Name = var.acr_name
  }
}
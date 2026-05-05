# User-assigned managed identity — attached to the VM so it can pull from ACR
# without storing any credentials on the instance.
resource "azurerm_user_assigned_identity" "app" {
  name                = "${var.prefix}-mi"
  resource_group_name = var.resource_group_name
  location            = var.location

  tags = {
    Name = "${var.prefix}-mi"
  }
}

# Grant the managed identity pull access to the container registry
resource "azurerm_role_assignment" "acr_pull" {
  scope                = var.acr_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}
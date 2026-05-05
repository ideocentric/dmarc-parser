output "managed_identity_id" {
  description = "Resource ID of the user-assigned managed identity — pass to the VM"
  value       = azurerm_user_assigned_identity.app.id
}

output "managed_identity_client_id" {
  description = "Client ID of the managed identity — used to authenticate to ACR on the VM"
  value       = azurerm_user_assigned_identity.app.client_id
}

output "managed_identity_principal_id" {
  description = "Principal ID of the managed identity — used for role assignments"
  value       = azurerm_user_assigned_identity.app.principal_id
}
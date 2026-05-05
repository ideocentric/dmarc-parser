output "acr_id" {
  description = "ACR resource ID — used to scope the AcrPull role assignment"
  value       = azurerm_container_registry.main.id
}

output "acr_name" {
  description = "ACR registry name"
  value       = azurerm_container_registry.main.name
}

output "login_server" {
  description = "ACR login server URL (e.g. dmarcprodacr.azurecr.io) — set as GitHub secret ACR_LOGIN_SERVER"
  value       = azurerm_container_registry.main.login_server
}
output "nsg_id" {
  description = "Network Security Group ID for the public subnet"
  value       = azurerm_network_security_group.app.id
}
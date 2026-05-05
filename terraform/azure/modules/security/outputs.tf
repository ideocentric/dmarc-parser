output "nsg_id" {
  description = "Network Security Group ID for the public subnet"
  value       = azurerm_network_security_group.app.id
}

output "db_nsg_id" {
  description = "DB Network Security Group ID for the private subnet (null for standalone)"
  value       = try(azurerm_network_security_group.db[0].id, null)
}
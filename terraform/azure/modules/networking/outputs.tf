output "vnet_id" {
  description = "Virtual network ID"
  value       = azurerm_virtual_network.main.id
}

output "vnet_address_space" {
  description = "VNet address space — used in NSG rules to restrict DB access to VNet traffic only"
  value       = azurerm_virtual_network.main.address_space[0]
}

output "public_subnet_id" {
  description = "Public subnet ID"
  value       = azurerm_subnet.public.id
}

output "private_subnet_id" {
  description = "Private subnet ID (null for standalone)"
  value       = try(azurerm_subnet.private[0].id, null)
}

output "db_delegated_subnet_id" {
  description = "Delegated PostgreSQL subnet ID (null when not split_managed)"
  value       = try(azurerm_subnet.db_delegated[0].id, null)
}
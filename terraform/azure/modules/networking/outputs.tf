output "vnet_id" {
  description = "Virtual network ID"
  value       = azurerm_virtual_network.main.id
}

output "public_subnet_id" {
  description = "Public subnet ID"
  value       = azurerm_subnet.public.id
}

output "vnet_address_space" {
  description = "VNet address space — useful for private NSG ingress rules"
  value       = azurerm_virtual_network.main.address_space[0]
}
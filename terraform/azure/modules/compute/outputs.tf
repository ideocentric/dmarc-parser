output "public_ip" {
  description = "Reserved static public IP address"
  value       = azurerm_public_ip.app.ip_address
}

output "vm_id" {
  description = "Azure VM resource ID"
  value       = azurerm_linux_virtual_machine.app.id
}

output "vm_name" {
  description = "Azure VM name"
  value       = azurerm_linux_virtual_machine.app.name
}

output "vm_size_used" {
  description = "Azure VM size that was deployed"
  value       = azurerm_linux_virtual_machine.app.size
}

output "private_ip" {
  description = "Private IP address of the VM within the VNet"
  value       = azurerm_network_interface.app.private_ip_address
}
output "public_ip" {
  description = "Public IPv4 address of the application Linode"
  value       = linode_instance.app.ip_address
}

output "instance_id" {
  description = "Linode instance ID"
  value       = linode_instance.app.id
}

output "instance_type_used" {
  description = "Linode instance type that was deployed"
  value       = linode_instance.app.type
}

output "vpc_ip" {
  description = "VPC IPv4 address (null for standalone mode)"
  # interface[0] is the VPC interface when create_vpc_iface is true.
  value = var.create_vpc_iface ? linode_instance.app.interface[0].ipv4[0].vpc : null
}
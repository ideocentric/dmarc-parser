output "vpc_id" {
  value = var.create_private_network ? linode_vpc.main[0].id : null
}

output "vpc_subnet_id" {
  value = var.create_private_network ? linode_vpc_subnet.private[0].id : null
}
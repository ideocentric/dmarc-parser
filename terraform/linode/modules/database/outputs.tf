locals {
  # split_vm: app connects to DB over the VPC interface (eth0 inside the DB Linode).
  # The VPC IP is auto-assigned from the subnet CIDR — read from the interface block.
  split_vm_vpc_ip = local.is_split_vm ? linode_instance.db[0].interface[0].ipv4[0].vpc : null

  # split_managed: Linode provides the hostname and auto-generated root password.
  managed_host     = local.is_split_managed ? linode_database_postgresql.main[0].host : null
  managed_password = local.is_split_managed ? linode_database_postgresql.main[0].root_password : null
  managed_port     = local.is_split_managed ? linode_database_postgresql.main[0].port : null

  db_host     = coalesce(local.split_vm_vpc_ip, local.managed_host, "localhost")
  db_port     = local.is_split_managed ? tostring(local.managed_port) : "5432"
  db_password = coalesce(local.managed_password, var.db_password, "")
}

output "db_host" {
  description = "Database host (VPC IP for split_vm, managed hostname for split_managed, empty for standalone)"
  value       = var.deployment_mode == "standalone" ? "" : local.db_host
}

output "database_url" {
  description = "Full DATABASE_URL for use in .env.prod"
  value = var.deployment_mode == "standalone" ? "" : (
    "postgresql://${var.db_username}:${local.db_password}@${local.db_host}:${local.db_port}/${var.db_name}"
  )
  sensitive = true
}

output "db_password" {
  description = "Database password — your supplied value for split_vm; auto-generated for split_managed"
  value       = local.db_password
  sensitive   = true
}
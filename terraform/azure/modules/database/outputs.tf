locals {
  split_vm_host      = try(azurerm_network_interface.db[0].private_ip_address, null)
  split_managed_host = try(azurerm_postgresql_flexible_server.main[0].fqdn, null)

  db_host = (
    local.split_vm_host != null      ? local.split_vm_host :
    local.split_managed_host != null ? local.split_managed_host :
    "db"  # Docker Compose service name for standalone
  )
}

output "db_host" {
  description = "Database host — private IP for split_vm, FQDN for split_managed, 'db' for standalone"
  value       = local.db_host
}

output "database_url" {
  description = "Full DATABASE_URL for .env.prod"
  value       = "postgresql+psycopg2://${var.db_admin_username}:${var.db_password}@${local.db_host}:5432/${var.db_name}"
  sensitive   = true
}
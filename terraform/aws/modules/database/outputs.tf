locals {
  # try() handles the case where a resource has count = 0 and the index doesn't exist
  split_vm_host      = try(aws_instance.db[0].private_ip, null)
  split_managed_host = try(aws_db_instance.main[0].address, null)

  db_host = (
    local.split_vm_host != null      ? local.split_vm_host :
    local.split_managed_host != null ? local.split_managed_host :
    "db"  # Docker Compose service name for standalone
  )
}

output "db_host" {
  description = "Database host — private IP for split_vm, RDS endpoint for split_managed, 'db' for standalone"
  value       = local.db_host
}

output "database_url" {
  description = "Full DATABASE_URL for .env.prod — set this in your application environment"
  value       = "postgresql+psycopg2://${var.db_username}:${var.db_password}@${local.db_host}:5432/${var.db_name}"
  sensitive   = true
}
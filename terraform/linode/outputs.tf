output "public_ip" {
  description = "Public IPv4 address of the application Linode"
  value       = module.compute.public_ip
}

output "instance_id" {
  description = "Linode instance ID"
  value       = module.compute.instance_id
}

output "instance_type_used" {
  description = "Linode instance type that was deployed"
  value       = module.compute.instance_type_used
}

output "ssh_command" {
  description = "SSH command to connect to the application server"
  value       = "ssh -i ${trimsuffix(var.ssh_public_key_path, ".pub")} root@${module.compute.public_ip}"
}

# ── Database (split topologies) ───────────────────────────────────────────────

output "db_host" {
  description = "Database hostname — use to verify connectivity or build DATABASE_URL manually"
  value       = module.database.db_host
}

output "database_url" {
  description = "Full DATABASE_URL — copy into .env.prod on the server"
  value       = module.database.database_url
  sensitive   = true
}

output "db_password" {
  description = "Database password — your supplied value for split_vm; auto-generated for split_managed"
  value       = module.database.db_password
  sensitive   = true
}

# ── CI/CD reference ───────────────────────────────────────────────────────────

output "deploy_note" {
  description = "CI/CD deployment note"
  value       = <<-EOT
    Linode has no SSM or managed container registry equivalent.
    Recommended CI/CD approach:
      1. Push images to Docker Hub or GitHub Container Registry (ghcr.io).
      2. SSH into the server and pull + restart via docker compose.
    Example GitHub Actions step:
      ssh root@${module.compute.public_ip} \
        "cd /opt/dmarc && docker compose pull && docker compose up -d"
  EOT
}
output "app_firewall_id" {
  value = linode_firewall.app.id
}

output "db_firewall_id" {
  value = var.deployment_mode != "standalone" ? linode_firewall.db[0].id : null
}
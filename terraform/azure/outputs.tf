output "public_ip" {
  description = "Reserved static public IP address — point your DNS A record here"
  value       = module.compute.public_ip
}

output "vm_id" {
  description = "Azure VM resource ID"
  value       = module.compute.vm_id
}

output "vm_name" {
  description = "Azure VM name — set as GitHub secret AZURE_VM_NAME"
  value       = module.compute.vm_name
}

output "resource_group_name" {
  description = "Resource group name — set as GitHub secret AZURE_RESOURCE_GROUP"
  value       = azurerm_resource_group.main.name
}

output "vm_size_used" {
  description = "Azure VM size that was deployed (reflects ClamAV auto-selection if no override)"
  value       = module.compute.vm_size_used
}

output "ssh_command" {
  description = "SSH command to connect to the VM"
  value       = "ssh -i ${trimsuffix(var.ssh_public_key_path, ".pub")} ${var.admin_username}@${module.compute.public_ip}"
}

# ── Container registry ────────────────────────────────────────────────────────

output "acr_login_server" {
  description = "ACR login server URL — set as GitHub secret ACR_LOGIN_SERVER"
  value       = module.registry.login_server
}

output "acr_api_repo" {
  description = "ACR API repository name — set as GitHub secret ACR_API_REPO"
  value       = "${module.registry.login_server}/dmarc-prod-api"
}

output "acr_frontend_repo" {
  description = "ACR frontend repository name — set as GitHub secret ACR_FRONTEND_REPO"
  value       = "${module.registry.login_server}/dmarc-prod-frontend"
}

# ── Managed identity ──────────────────────────────────────────────────────────

output "managed_identity_client_id" {
  description = "Managed identity client ID — used by the VM to authenticate to ACR"
  value       = module.iam.managed_identity_client_id
}
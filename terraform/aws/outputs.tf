output "public_ip" {
  description = "Reserved Elastic IP address for the application server"
  value       = module.compute.public_ip
}

output "instance_id" {
  description = "EC2 instance ID"
  value       = module.compute.instance_id
}

output "vpc_id" {
  description = "VPC ID"
  value       = module.networking.vpc_id
}

output "key_pair_name" {
  description = "AWS key pair name associated with the instance"
  value       = module.compute.key_pair_name
}

output "ssh_command" {
  description = "SSH command to connect to the application server"
  value       = "ssh -i ${trimsuffix(var.ssh_public_key_path, ".pub")} ubuntu@${module.compute.public_ip}"
}

output "instance_type_used" {
  description = "EC2 instance type that was deployed"
  value       = module.compute.instance_type_used
}

# ── ECR ───────────────────────────────────────────────────────────────────────

output "ecr_registry_url" {
  description = "ECR registry URL — set as GitHub secret ECR_REGISTRY"
  value       = module.registry.registry_url
}

output "ecr_api_repo" {
  description = "ECR API repository name — set as GitHub secret ECR_API_REPO"
  value       = module.registry.api_repo_name
}

output "ecr_frontend_repo" {
  description = "ECR frontend repository name — set as GitHub secret ECR_FRONTEND_REPO"
  value       = module.registry.frontend_repo_name
}

# ── CI/CD user (only populated when create_ci_user = true) ───────────────────

output "ci_user_access_key_id" {
  description = "CI IAM access key ID — set as GitHub secret AWS_ACCESS_KEY_ID"
  value       = module.iam.ci_access_key_id
}

output "ci_user_secret_access_key" {
  description = "CI IAM secret access key — set as GitHub secret AWS_SECRET_ACCESS_KEY"
  value       = module.iam.ci_secret_access_key
  sensitive   = true
}

# ── Database (split topologies) ───────────────────────────────────────────────

output "db_host" {
  description = "Database host — use to verify connectivity or set DATABASE_URL manually"
  value       = module.database.db_host
}

output "database_url" {
  description = "Full DATABASE_URL — copy into .env.prod on the server"
  value       = module.database.database_url
  sensitive   = true
}
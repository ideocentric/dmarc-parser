output "registry_url" {
  description = "ECR registry URL (account + region endpoint, no repo suffix)"
  value       = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.name}.amazonaws.com"
}

output "api_repo_name" {
  description = "ECR repository name for the API/backend image"
  value       = aws_ecr_repository.api.name
}

output "frontend_repo_name" {
  description = "ECR repository name for the frontend image"
  value       = aws_ecr_repository.frontend.name
}

output "api_repo_url" {
  description = "Full ECR URL for the API image (registry/repo)"
  value       = aws_ecr_repository.api.repository_url
}

output "frontend_repo_url" {
  description = "Full ECR URL for the frontend image (registry/repo)"
  value       = aws_ecr_repository.frontend.repository_url
}
output "instance_profile_name" {
  description = "IAM instance profile name — attach to the EC2 to enable ECR pull and SSM access"
  value       = aws_iam_instance_profile.ec2.name
}

output "instance_role_arn" {
  description = "IAM role ARN for the EC2 instance"
  value       = aws_iam_role.ec2.arn
}

output "ci_user_name" {
  description = "CI IAM user name (null when create_ci_user = false)"
  value       = var.create_ci_user ? aws_iam_user.ci[0].name : null
}

output "ci_access_key_id" {
  description = "CI IAM access key ID — store as GitHub secret AWS_ACCESS_KEY_ID (null when create_ci_user = false)"
  value       = var.create_ci_user ? aws_iam_access_key.ci[0].id : null
}

output "ci_secret_access_key" {
  description = "CI IAM secret access key — store as GitHub secret AWS_SECRET_ACCESS_KEY (null when create_ci_user = false)"
  value       = var.create_ci_user ? aws_iam_access_key.ci[0].secret : null
  sensitive   = true
}
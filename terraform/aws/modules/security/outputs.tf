output "app_sg_id" {
  description = "Security group ID for the application server"
  value       = aws_security_group.app.id
}
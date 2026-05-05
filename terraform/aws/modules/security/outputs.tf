output "app_sg_id" {
  description = "Security group ID for the application server"
  value       = aws_security_group.app.id
}

output "db_sg_id" {
  description = "Security group ID for the database (null for standalone)"
  value       = try(aws_security_group.db[0].id, null)
}
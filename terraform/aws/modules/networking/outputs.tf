output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "vpc_cidr" {
  description = "VPC CIDR block"
  value       = aws_vpc.main.cidr_block
}

output "public_subnet_id" {
  description = "Public subnet ID"
  value       = aws_subnet.public.id
}

output "private_subnet_id" {
  description = "Primary private subnet ID (null for standalone)"
  value       = try(aws_subnet.private[0].id, null)
}

output "private_subnet_ids" {
  description = "All private subnet IDs across both AZs (required for RDS subnet groups)"
  value       = [for s in aws_subnet.private : s.id]
}
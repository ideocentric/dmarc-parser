output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "public_subnet_id" {
  description = "Public subnet ID"
  value       = aws_subnet.public.id
}

output "vpc_cidr" {
  description = "VPC CIDR block — useful for private security group ingress rules"
  value       = aws_vpc.main.cidr_block
}
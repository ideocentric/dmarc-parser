output "public_ip" {
  description = "Reserved Elastic IP address"
  value       = aws_eip.app.public_ip
}

output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.app.id
}

output "key_pair_name" {
  description = "Name of the AWS key pair associated with the instance"
  value       = aws_key_pair.main.key_name
}

output "instance_type_used" {
  description = "EC2 instance type that was deployed"
  value       = aws_instance.app.instance_type
}

output "private_ip" {
  description = "Private IP address of the instance within the VPC"
  value       = aws_instance.app.private_ip
}
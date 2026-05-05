# Latest Ubuntu 24.04 LTS (Noble Numbat) x86_64 AMI from Canonical
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# Upload the public key to AWS — private key stays on the operator's machine
resource "aws_key_pair" "main" {
  key_name   = "${var.prefix}-keypair"
  public_key = file(pathexpand(var.ssh_public_key_path))

  tags = {
    Name = "${var.prefix}-keypair"
  }
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [var.security_group_id]
  key_name               = aws_key_pair.main.key_name
  iam_instance_profile   = var.iam_instance_profile_name

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_disk_gb
    encrypted             = true
    delete_on_termination = true

    tags = {
      Name = "${var.prefix}-root-vol"
    }
  }

  # IMDSv2 required — disables the less-secure IMDSv1 token-optional path
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  user_data = <<-EOF
    #!/bin/bash
    set -euo pipefail

    # System update
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get upgrade -y

    # Docker prerequisites
    apt-get install -y ca-certificates curl gnupg

    # Docker GPG key and repository
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      | tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Install Docker Engine + Compose plugin
    apt-get update -y
    apt-get install -y \
      docker-ce \
      docker-ce-cli \
      containerd.io \
      docker-buildx-plugin \
      docker-compose-plugin

    # Allow ubuntu user to run docker without sudo
    usermod -aG docker ubuntu

    # Enable Docker on boot
    systemctl enable docker
    systemctl start docker

    # Application directory — contents deployed separately via docker-compose
    mkdir -p /opt/dmarc
    chown ubuntu:ubuntu /opt/dmarc
  EOF

  # Changing user_data after initial deployment does NOT re-provision the running instance.
  # Set to true only if you intend a full instance replacement on user_data changes.
  user_data_replace_on_change = false

  tags = {
    Name        = "${var.prefix}-app-ec2"
    Environment = var.environment
  }
}

# Reserved public IP — persists across instance stop/start cycles
resource "aws_eip" "app" {
  domain = "vpc"

  tags = {
    Name = "${var.prefix}-eip"
  }
}

resource "aws_eip_association" "app" {
  instance_id   = aws_instance.app.id
  allocation_id = aws_eip.app.id
}
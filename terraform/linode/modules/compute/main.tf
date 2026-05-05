# Bootstrap StackScript — installs Docker CE + Compose plugin and creates /opt/dmarc.
# StackScripts run once on first boot and are universally supported across all
# Linode regions (unlike the metadata service which requires newer regions).

resource "linode_stackscript" "docker_bootstrap" {
  label       = "${var.prefix}-docker-bootstrap"
  description = "Install Docker CE and Docker Compose plugin; create /opt/dmarc"
  images      = ["linode/ubuntu24.04"]
  is_public   = false

  script = <<-'SCRIPT'
    #!/bin/bash
    set -euo pipefail

    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get upgrade -y

    apt-get install -y ca-certificates curl gnupg

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -y
    apt-get install -y \
      docker-ce \
      docker-ce-cli \
      containerd.io \
      docker-buildx-plugin \
      docker-compose-plugin

    systemctl enable docker
    systemctl start docker

    mkdir -p /opt/dmarc
  SCRIPT
}

resource "linode_instance" "app" {
  label           = "${var.prefix}-app"
  region          = var.region
  type            = var.instance_type
  image           = "linode/ubuntu24.04"
  authorized_keys = [trimspace(var.ssh_public_key)]
  firewall_id     = var.firewall_id
  stackscript_id  = linode_stackscript.docker_bootstrap.id

  tags = [var.prefix, var.environment, "app"]

  # Split topologies: add a VPC interface for private DB communication, then the
  # public interface. Order matters — VPC is listed first so it gets eth0 inside
  # the instance; public gets eth1 (or vice versa depending on Linode's assignment).
  # The app connects to the DB over the VPC IP; all HTTP/SSH traffic uses public.

  dynamic "interface" {
    for_each = var.create_vpc_iface ? [1] : []
    content {
      purpose   = "vpc"
      subnet_id = var.vpc_subnet_id
    }
  }

  dynamic "interface" {
    for_each = var.create_vpc_iface ? [1] : []
    content {
      purpose = "public"
    }
  }
}
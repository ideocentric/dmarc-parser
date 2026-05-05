# VPC and private subnet — only created for split topologies.
# Standalone mode communicates entirely over localhost inside the Linode.

resource "linode_vpc" "main" {
  count  = var.create_private_network ? 1 : 0
  label  = "${var.prefix}-vpc"
  region = var.region
}

resource "linode_vpc_subnet" "private" {
  count  = var.create_private_network ? 1 : 0
  vpc_id = linode_vpc.main[0].id
  label  = "${var.prefix}-private-subnet"
  ipv4   = var.vpc_subnet_cidr
}
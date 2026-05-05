data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  az   = coalesce(var.availability_zone, data.aws_availability_zones.available.names[0])
  az_2 = data.aws_availability_zones.available.names[1]
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.prefix}-vpc"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.prefix}-igw"
  }
}

# ── Public subnet ─────────────────────────────────────────────────────────────

resource "aws_subnet" "public" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.public_subnet_cidr
  availability_zone = local.az

  map_public_ip_on_launch = false

  tags = {
    Name = "${var.prefix}-public-subnet"
    Tier = "public"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.prefix}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# ── Private subnets + NAT Gateway (split topologies only) ─────────────────────
# Two private subnets across different AZs are required by RDS subnet groups.
# split_vm uses private-subnet-1; split_managed uses both for the subnet group.

resource "aws_eip" "nat" {
  count  = var.create_private_network ? 1 : 0
  domain = "vpc"

  tags = {
    Name = "${var.prefix}-nat-eip"
  }
}

resource "aws_nat_gateway" "main" {
  count         = var.create_private_network ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public.id

  tags = {
    Name = "${var.prefix}-nat-gw"
  }

  depends_on = [aws_internet_gateway.main]
}

resource "aws_subnet" "private" {
  count             = var.create_private_network ? 1 : 0
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidr
  availability_zone = local.az

  tags = {
    Name = "${var.prefix}-private-subnet"
    Tier = "private"
  }
}

resource "aws_subnet" "private_2" {
  count             = var.create_private_network ? 1 : 0
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidr_2
  availability_zone = local.az_2

  tags = {
    Name = "${var.prefix}-private-subnet-2"
    Tier = "private"
  }
}

resource "aws_route_table" "private" {
  count  = var.create_private_network ? 1 : 0
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[0].id
  }

  tags = {
    Name = "${var.prefix}-private-rt"
  }
}

resource "aws_route_table_association" "private" {
  count          = var.create_private_network ? 1 : 0
  subnet_id      = aws_subnet.private[0].id
  route_table_id = aws_route_table.private[0].id
}

resource "aws_route_table_association" "private_2" {
  count          = var.create_private_network ? 1 : 0
  subnet_id      = aws_subnet.private_2[0].id
  route_table_id = aws_route_table.private[0].id
}
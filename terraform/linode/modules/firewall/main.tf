# ── Application server firewall ───────────────────────────────────────────────

resource "linode_firewall" "app" {
  label           = "${var.prefix}-app-fw"
  inbound_policy  = "DROP"
  outbound_policy = "ACCEPT"

  inbound {
    label    = "allow-ssh-admin"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = "22"
    ipv4     = [var.admin_cidr]
  }

  inbound {
    label    = "allow-http"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = "80"
    ipv4     = ["0.0.0.0/0"]
    ipv6     = ["::/0"]
  }

  inbound {
    label    = "allow-https"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = "443"
    ipv4     = ["0.0.0.0/0"]
    ipv6     = ["::/0"]
  }
}

# ── Database firewall (split topologies only) ─────────────────────────────────
# Allows SSH from the operator's IP and PostgreSQL only from the private VPC
# subnet CIDR — the public internet cannot reach port 5432.

resource "linode_firewall" "db" {
  count           = var.deployment_mode != "standalone" ? 1 : 0
  label           = "${var.prefix}-db-fw"
  inbound_policy  = "DROP"
  outbound_policy = "ACCEPT"

  inbound {
    label    = "allow-ssh-admin"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = "22"
    ipv4     = [var.admin_cidr]
  }

  inbound {
    label    = "allow-postgres-vpc"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = "5432"
    ipv4     = [var.vpc_subnet_cidr]
  }
}
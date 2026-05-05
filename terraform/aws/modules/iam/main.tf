# ── EC2 instance role ─────────────────────────────────────────────────────────
# Allows the EC2 to pull from ECR and be managed via SSM without SSH access.

resource "aws_iam_role" "ec2" {
  name = "${var.prefix}-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })

  tags = {
    Name = "${var.prefix}-ec2-role"
  }
}

# Pull images from ECR without stored credentials
resource "aws_iam_role_policy_attachment" "ecr_read" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# SSM Session Manager — alternative to SSH, no port 22 required
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${var.prefix}-ec2-profile"
  role = aws_iam_role.ec2.name

  tags = {
    Name = "${var.prefix}-ec2-profile"
  }
}

# ── CI/CD IAM user (optional — prefer OIDC for GitHub Actions) ───────────────
# Set create_ci_user = true to create a long-lived access key for CI.
# The recommended alternative is GitHub Actions OIDC (no stored secrets):
# https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services

resource "aws_iam_user" "ci" {
  count = var.create_ci_user ? 1 : 0
  name  = "${var.prefix}-ci-user"

  tags = {
    Name = "${var.prefix}-ci-user"
  }
}

resource "aws_iam_user_policy" "ci_ecr_push" {
  count = var.create_ci_user ? 1 : 0
  name  = "${var.prefix}-ci-ecr-push"
  user  = aws_iam_user.ci[0].name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # GetAuthorizationToken is global — cannot be scoped to a specific repo
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload"
        ]
        Resource = var.ecr_repository_arns
      },
      {
        # Allow CI to trigger SSM run commands for deployment
        Effect   = "Allow"
        Action   = ["ssm:SendCommand", "ssm:GetCommandInvocation"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_access_key" "ci" {
  count = var.create_ci_user ? 1 : 0
  user  = aws_iam_user.ci[0].name
}
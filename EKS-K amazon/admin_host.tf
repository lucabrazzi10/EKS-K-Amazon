data "aws_caller_identity" "current" {}

# Latest Amazon Linux 2 AMI
data "aws_ami" "amazon_linux2" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

############################################
# Security Group for Admin Host
############################################
resource "aws_security_group" "admin_host_sg" {
  name        = "${var.name}-admin-host-sg"
  description = "Admin host SG (SSM only, no inbound)"
  vpc_id      = aws_vpc.this.id

  # No inbound rules at all (SSM does not require inbound)


  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.name}-admin-host-sg" }
}

############################################
# IAM Role/Instance Profile for Admin Host
############################################
data "aws_iam_policy_document" "admin_host_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "admin_host_role" {
  name               = "${var.name}-admin-host-role"
  assume_role_policy = data.aws_iam_policy_document.admin_host_assume.json
}

# SSM access (mandatory)
resource "aws_iam_role_policy_attachment" "admin_host_ssm" {
  role       = aws_iam_role.admin_host_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Minimal EKS read to build kubeconfig (describe cluster)
resource "aws_iam_role_policy" "admin_host_eks_read" {
  name = "${var.name}-admin-host-eks-read"
  role = aws_iam_role.admin_host_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EksDescribe"
        Effect = "Allow"
        Action = [
          "eks:DescribeCluster",
          "eks:ListClusters"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "admin_host_profile" {
  name = "${var.name}-admin-host-profile"
  role = aws_iam_role.admin_host_role.name
}

############################################
# Admin Host EC2 (Private Subnet, No Public IP)
############################################
resource "aws_instance" "admin_host" {
  ami                    = data.aws_ami.amazon_linux2.id
  instance_type          = "t3.small"
  subnet_id              = values(aws_subnet.private)[0].id
  vpc_security_group_ids = [aws_security_group.admin_host_sg.id]

  associate_public_ip_address = false

  iam_instance_profile = aws_iam_instance_profile.admin_host_profile.name

  user_data = <<-EOF
              #!/bin/bash
              set -euo pipefail

              yum update -y
              yum install -y jq git

              # Install AWS CLI v2 (Amazon Linux 2 sometimes has v1 by default)
              curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "/tmp/awscliv2.zip"
              unzip -q /tmp/awscliv2.zip -d /tmp
              /tmp/aws/install || true

              # Install kubectl matching EKS best-practice (grab latest stable)
              KVER="$(curl -sL https://dl.k8s.io/release/stable.txt)"
              curl -sL "https://dl.k8s.io/release/$${KVER}/bin/linux/amd64/kubectl" -o /usr/local/bin/kubectl

              chmod +x /usr/local/bin/kubectl

              # Create kubeconfig for ec2-user
              su - ec2-user -c "aws eks update-kubeconfig --region ${var.aws_region} --name ${aws_eks_cluster.this.name}"

              # Quick sanity check (will fail until aws-auth maps role/user, that’s expected)
              su - ec2-user -c "kubectl version --client=true"
              EOF

  tags = {
    Name = "${var.name}-admin-host"
  }

  depends_on = [
    aws_eks_cluster.this,
    aws_iam_role_policy_attachment.admin_host_ssm
  ]
}

############################################
# Outputs
############################################
output "admin_host_instance_id" {
  value = aws_instance.admin_host.id
}

# Grant the admin host IAM role access to the cluster using EKS access entries (no kubectl needed)

resource "aws_eks_access_entry" "admin_host" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = aws_iam_role.admin_host_role.arn
  type          = "STANDARD"
}

resource "aws_eks_access_policy_association" "admin_host_cluster_admin" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = aws_iam_role.admin_host_role.arn

  policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"

  access_scope {
    type = "cluster"
  }
}

resource "aws_eks_cluster" "this" {
  name     = "${var.name}-cluster"
  role_arn = aws_iam_role.eks_cluster_role.arn
  version  = var.cluster_version

  vpc_config {
    subnet_ids              = concat([for s in aws_subnet.private : s.id], [for s in aws_subnet.public : s.id])
    security_group_ids      = [aws_security_group.eks_cluster_sg.id]

    endpoint_private_access = true
    endpoint_public_access  = false
  }
    # ✅ REQUIRED for aws_eks_access_entry / access policy associations
  access_config {
    authentication_mode                         = "API_AND_CONFIG_MAP"
    bootstrap_cluster_creator_admin_permissions = true
  }


  depends_on = [
    aws_iam_role_policy_attachment.eks_cluster_policy
  ]

  tags = {
    Name = "${var.name}-cluster"
  }
}

resource "aws_launch_template" "eks_nodes" {
  name_prefix = "${var.name}-eks-nodes-"

  vpc_security_group_ids = [
    aws_security_group.eks_node_sg.id
  ]

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "${var.name}-eks-node"
    }
  }
}

resource "aws_eks_node_group" "this" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "${var.name}-ng"
  node_role_arn   = aws_iam_role.eks_node_role.arn

  subnet_ids = [for s in values(aws_subnet.private) : s.id]

  instance_types = var.node_instance_types

  scaling_config {
    desired_size = var.desired_size
    min_size     = var.min_size
    max_size     = var.max_size
  }

  launch_template {
    id      = aws_launch_template.eks_nodes.id
    version = "$Latest"
  }

  update_config {
    max_unavailable = 1
  }

  tags = {
    Name = "${var.name}-ng"
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node_policy,
    aws_iam_role_policy_attachment.eks_cni_policy,
    aws_iam_role_policy_attachment.ecr_readonly_policy,
    aws_iam_role_policy_attachment.ssm_managed_instance_core
  ]
}


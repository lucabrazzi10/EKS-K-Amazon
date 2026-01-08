# Cluster security group: no public ingress
resource "aws_security_group" "eks_cluster_sg" {
  name        = "${var.name}-eks-cluster-sg"
  description = "EKS control plane security group"
  vpc_id      = aws_vpc.this.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.name}-eks-cluster-sg" }
}

# Node security group: allow cluster -> node, and node <-> node
resource "aws_security_group" "eks_node_sg" {
  name        = "${var.name}-eks-node-sg"
  description = "EKS worker nodes security group"
  vpc_id      = aws_vpc.this.id

  # Node-to-node traffic (required for CNI/pods etc.)
  ingress {
    from_port = 0
    to_port   = 0
    protocol  = "-1"
    self      = true
  }

  # Control plane -> kubelet
  ingress {
    from_port                = 10250
    to_port                  = 10250
    protocol                 = "tcp"
    security_groups          = [aws_security_group.eks_cluster_sg.id]
    description              = "Control plane to kubelet"
  }

  # Control plane -> nodes (webhook/extensions). Keep tight.
  ingress {
    from_port                = 443
    to_port                  = 443
    protocol                 = "tcp"
    security_groups          = [aws_security_group.eks_cluster_sg.id]
    description              = "Control plane to nodes https"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.name}-eks-node-sg" }
}
resource "aws_security_group_rule" "nodes_to_cluster_api" {
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  security_group_id        = aws_security_group.eks_cluster_sg.id
  source_security_group_id = aws_security_group.eks_node_sg.id
  description              = "Worker nodes to EKS API server"
}
# Allow the admin host (SSM box) to talk to the EKS API endpoint (private)
resource "aws_security_group_rule" "admin_to_eks_api_443" {
  description              = "Admin host to EKS API (443)"
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"

  security_group_id        = aws_security_group.eks_cluster_sg.id
  source_security_group_id = aws_security_group.admin_host_sg.id
}

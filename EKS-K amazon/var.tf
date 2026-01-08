variable "aws_region" {
  type    = string
  default = "us-west-2"
}

variable "name" {
  type    = string
  default = "rgs-core-dev"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "azs" {
  type    = list(string)
  default = ["us-west-2a", "us-west-2b"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.10.0/24", "10.0.20.0/24"]
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.110.0/24", "10.0.120.0/24"]
}

variable "cluster_version" {
  type    = string
  default = "1.29"
}

variable "node_instance_types" {
  type    = list(string)
  default = ["t3.medium"]
}

variable "desired_size" {
  type    = number
  default = 2
}

variable "min_size" {
  type    = number
  default = 2
}

variable "max_size" {
  type    = number
  default = 4
}
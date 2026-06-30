# VPC — terraform-aws-modules/vpc. NAT Gateway 끔(비용), 대신 NAT Instance(nat.tf) + Gateway Endpoint.
# project-draft 22번: NAT Gateway($32.85/월) 제거 → NAT Instance(t4g.nano ~$3) + S3·DynamoDB Gateway Endpoint(무료).

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.13"

  name = "${var.project}-shared"
  cidr = var.vpc_cidr
  azs  = var.azs

  public_subnets  = [for i in range(length(var.azs)) : cidrsubnet(var.vpc_cidr, 8, i)]
  private_subnets = [for i in range(length(var.azs)) : cidrsubnet(var.vpc_cidr, 8, i + 10)]

  enable_nat_gateway   = false # NAT Instance로 대체(nat.tf)
  enable_dns_hostnames = true
  enable_dns_support   = true

  # EKS 로드밸런서 서브넷 디스커버리 태그
  public_subnet_tags  = { "kubernetes.io/role/elb" = 1 }
  private_subnet_tags = { "kubernetes.io/role/internal-elb" = 1 }
}

# S3·DynamoDB Gateway Endpoint(무료) — private subnet의 S3/DDB 트래픽이 NAT 우회
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = module.vpc.vpc_id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = module.vpc.private_route_table_ids
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = module.vpc.vpc_id
  service_name      = "com.amazonaws.${var.region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = module.vpc.private_route_table_ids
}

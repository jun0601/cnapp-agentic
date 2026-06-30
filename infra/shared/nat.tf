# NAT Instance (raw) — 비용 최적화(project-draft 22번). NAT Gateway($32/월) 대신 NAT Instance(t4g.nano ~$3).
# fck-nat 공개 AMI를 raw aws_instance로 띄움(모듈 미사용 → provider 버전 충돌·변수명 불확실성 제거).
# private subnet 아웃바운드(EKS 노드 이미지 pull·EKS API·Bedrock·외부 API)에 사용. S3/DynamoDB는 Gateway Endpoint(무료).
#
# ⚠️ apply 전 확인:
#   - nat_ami_owner(fck-nat 퍼블리셔 계정) 값이 맞는지 검증. 안 맞으면 data.aws_ami가 빈 결과 → apply 실패.
#     대안: 직접 빌드한 NAT AMI 또는 AL2023 + user_data(ip_forward·iptables MASQUERADE).
#   - 데모 외 기간엔 인스턴스 중지 또는 destroy(비용).

data "aws_ami" "fck_nat" {
  most_recent = true
  owners      = [var.nat_ami_owner]

  filter {
    name   = "name"
    values = ["fck-nat-al2023-*-arm64-ebs"]
  }

  filter {
    name   = "architecture"
    values = ["arm64"]
  }
}

resource "aws_security_group" "nat" {
  name        = "${var.project}-nat"
  description = "NAT instance — VPC 내부에서 들어와 인터넷으로 나감"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "from VPC private subnets"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "nat" {
  ami                         = data.aws_ami.fck_nat.id
  instance_type               = "t4g.nano"
  subnet_id                   = module.vpc.public_subnets[0]
  associate_public_ip_address = true
  source_dest_check           = false # NAT 핵심 — 자기 IP 아닌 트래픽 포워딩 허용
  vpc_security_group_ids      = [aws_security_group.nat.id]

  tags = { Name = "${var.project}-nat" }
}

# private route table 0.0.0.0/0 → NAT instance (S3/DDB는 Gateway Endpoint가 더 구체적 경로라 우선)
resource "aws_route" "private_nat" {
  count                  = length(module.vpc.private_route_table_ids)
  route_table_id         = module.vpc.private_route_table_ids[count.index]
  destination_cidr_block = "0.0.0.0/0"
  network_interface_id   = aws_instance.nat.primary_network_interface_id
}

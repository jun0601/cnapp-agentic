# RDS PostgreSQL t3.micro + pgvector — 벡터DB + findings 저장 동거(D9·24번 확정).
# private subnet, VPC Lambda/EKS에서만 접근. RDS Proxy 미사용(비용). 마스터 비번 Secrets Manager.

resource "random_password" "db" {
  length  = 24
  special = true
  # RDS가 못 받는 문자 제외
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_secretsmanager_secret" "db" {
  name        = "${var.project}/rds/master"
  description = "RDS pgvector master credential (shared)"
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db.result
    dbname   = var.db_name
  })
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.project}-db"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "rds" {
  name        = "${var.project}-rds"
  description = "RDS pgvector — VPC 내부에서만 5432"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "PostgreSQL from VPC (Lambda VPC + EKS). TODO: 소스 SG로 좁히기"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# pgvector는 확장(extension) — shared_preload 불필요. 앱/마이그레이션에서 CREATE EXTENSION IF NOT EXISTS vector;
resource "aws_db_parameter_group" "pg" {
  name   = "${var.project}-pg16"
  family = "postgres16"
}

resource "aws_db_instance" "pgvector" {
  identifier     = "${var.project}-pgvector"
  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  allocated_storage     = 20
  max_allocated_storage = 50
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result

  db_subnet_group_name    = aws_db_subnet_group.this.name
  vpc_security_group_ids  = [aws_security_group.rds.id]
  parameter_group_name    = aws_db_parameter_group.pg.name
  multi_az                = false
  publicly_accessible     = false
  backup_retention_period = 1

  skip_final_snapshot = true  # 데모
  deletion_protection = false # 데모
}

# 비용 가드레일(진우 결정): RDS Stop은 최대 7일 후 AWS가 자동 재기동 → EventBridge Scheduler + Lambda로
# 매일 새벽 'available'이면 자동 Stop. 별도 리소스로 추가 예정(infra/shared 또는 ops 모듈).
# TODO: aws_scheduler_schedule + aws_lambda_function(rds:StopDBInstance) 추가.

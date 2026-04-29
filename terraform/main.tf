terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ── SSH Key Pair ──────────────────────────────────────────────────────────────
resource "aws_key_pair" "mqtt_key" {
  key_name   = "mqtt-ci-key"
  public_key = var.ssh_public_key
}

# ── Security Group ────────────────────────────────────────────────────────────
resource "aws_security_group" "mqtt_test_sg" {
  name        = "mqtt-test-sg"
  description = "Allow MQTT and SSH traffic for CI test runner"

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "MQTT"
    from_port   = 1883
    to_port     = 1883
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "MQTT WebSocket"
    from_port   = 9001
    to_port     = 9001
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "mqtt-test-sg"
    Project     = "mqtt-ec2-ci"
    Environment = var.environment
  }
}

# ── Latest Ubuntu 22.04 AMI ───────────────────────────────────────────────────
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
}

# ── EC2 Instance ──────────────────────────────────────────────────────────────
resource "aws_instance" "mqtt_test_runner" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.mqtt_key.key_name
  vpc_security_group_ids = [aws_security_group.mqtt_test_sg.id]

  user_data = <<-EOF
    #!/bin/bash
    set -e

    # Install Docker from official Docker repo
    apt-get update -y
    apt-get install -y ca-certificates curl gnupg

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

    systemctl enable docker
    systemctl start docker
    usermod -aG docker ubuntu

    echo "Bootstrap complete" > /home/ubuntu/bootstrap.log
  EOF

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }

  tags = {
    Name        = "mqtt-test-runner"
    Project     = "mqtt-ec2-ci"
    Environment = var.environment
  }
}
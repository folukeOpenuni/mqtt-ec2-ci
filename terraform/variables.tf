variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "eu-west-1"
}

variable "environment" {
  description = "Deployment environment label"
  type        = string
  default     = "ci"
}

variable "instance_type" {
  description = "EC2 instance type for the test runner"
  type        = string
  default     = "t3.micro"
}

variable "ssh_public_key" {
  description = "Public SSH key injected into EC2 for CI runner access"
  type        = string
  sensitive   = true
}
# ⚠️ SECURITY TEST FILE (DO NOT USE IN PRODUCTION)
# This file is used to verify that the GitHub Security Tab is correctly receiving
# and displaying vulnerabilities found during the Static Analysis (Gate 1) phase.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

resource "aws_s3_bucket" "vulnerable_test_bucket" {
  bucket = "vulnerable-security-test-bucket"
}

# Blatant security violation: Public-read ACL (AVD-AWS-0089)
resource "aws_s3_bucket_acl" "vulnerable_test_acl" {
  bucket = aws_s3_bucket.vulnerable_test_bucket.id
  acl    = "public-read"
}

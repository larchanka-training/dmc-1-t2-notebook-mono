output "cloudfront_domain_name" {
  description = "CloudFront domain (the public app URL until a custom domain is added)."
  value       = aws_cloudfront_distribution.this.domain_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidations)."
  value       = aws_cloudfront_distribution.this.id
}

output "frontend_bucket" {
  description = "S3 bucket for the frontend build (s3 sync target)."
  value       = aws_s3_bucket.frontend.bucket
}

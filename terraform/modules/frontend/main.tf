# Frontend delivery: a private S3 bucket holding the built React app, served
# through CloudFront. CloudFront routes /api/v1/* to the API ALB and everything
# else to S3 (with a CloudFront Function for SPA routing).
#
# The static-S3 side is network-independent and applies on its own; the
# distribution depends on the ALB DNS (Phase 1 → VPC), so it materializes once
# the backend exists. TLS uses either the default *.cloudfront.net cert (when
# acm_certificate_arn is null) or a custom ACM cert in us-east-1 covering the
# names in aliases.
#
# Uploading the build (vite build -> s3 sync) + invalidation is a CI deploy step,
# not Terraform.

# --- S3 (private, CloudFront-only) ---------------------------------------

resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project}-frontend"
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  versioning_configuration {
    status = "Enabled"
  }
}

# --- CloudFront access to the private bucket ------------------------------

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project}-frontend-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# SPA routing: requests without a file extension are rewritten to /index.html
# so client-side routes resolve. Static assets (with an extension) pass through.
resource "aws_cloudfront_function" "spa" {
  name    = "${var.project}-spa-rewrite"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = <<-EOT
    function handler(event) {
      var request = event.request;
      if (!request.uri.includes('.')) {
        request.uri = '/index.html';
      }
      return request;
    }
  EOT
}

# Managed policies (modern replacement for the deprecated forwarded_values).
data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

# --- CloudFront distribution ---------------------------------------------

resource "aws_cloudfront_distribution" "this" {
  enabled             = true
  comment             = "${var.project} frontend"
  default_root_object = "index.html"
  price_class         = var.price_class
  aliases             = var.aliases

  origin {
    origin_id                = "s3-frontend"
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  origin {
    origin_id   = "api-alb"
    domain_name = var.alb_dns_name

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only" # ALB is HTTP until the TLS phase
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # /* -> S3 static, with SPA rewrite.
  default_cache_behavior {
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa.arn
    }
  }

  # /api/v1/* -> ALB, no caching, forward everything (except Host).
  ordered_cache_behavior {
    path_pattern             = "/api/v1/*"
    target_origin_id         = "api-alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # Default *.cloudfront.net certificate when acm_certificate_arn is null;
  # custom ACM cert (must be in us-east-1) when provided. Aliases must be a
  # subset of the cert's SAN list, or CloudFront will reject the apply.
  viewer_certificate {
    cloudfront_default_certificate = var.acm_certificate_arn == null
    acm_certificate_arn            = var.acm_certificate_arn
    ssl_support_method             = var.acm_certificate_arn != null ? "sni-only" : null
    minimum_protocol_version       = var.acm_certificate_arn != null ? "TLSv1.2_2021" : null
  }

  lifecycle {
    precondition {
      condition     = length(var.aliases) == 0 || var.acm_certificate_arn != null
      error_message = "frontend module: aliases requires acm_certificate_arn — CloudFront cannot serve custom domain names without a matching certificate."
    }
  }
}

# --- Bucket policy: only this CloudFront distribution may read ------------

data "aws_iam_policy_document" "frontend_s3" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.this.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_s3.json
}

# Bedrock access for the API task.
#
# Two pieces live here:
#   1. A least-privilege IAM policy on the task role that lets the running
#      container invoke the two Nova models (generation + injection guard) via
#      their EU cross-region inference profiles.
#   2. Account-wide model-invocation logging to CloudWatch — metadata ONLY
#      (no prompt/completion bodies), per docs/ai-architecture.md §8.5.
#
# The private network path (a bedrock-runtime VPC interface endpoint) is NOT
# here — it belongs with the VPC/subnets/SGs in the network module
# (modules/network/bedrock_endpoint.tf).

data "aws_caller_identity" "current" {}

locals {
  # The model IDs we actually call — EU Geo inference profiles (the "eu." prefix
  # routes the request across the EU region group). Nova Micro has no In-Region
  # option in eu-north-1, so the Geo profile is the only path that works for both.
  bedrock_profile_ids = [
    var.bedrock_generator_model_id, # Nova Lite — code generation
    var.bedrock_guard_model_id,     # Nova Micro — prompt-injection pre-filter
  ]

  # Bare foundation-model IDs = the profile ID without the "eu." geo prefix.
  bedrock_model_ids = [for id in local.bedrock_profile_ids : trimprefix(id, "eu.")]

  # Resources the task may invoke. Cross-region inference needs BOTH:
  #   (1) the inference-profile ARN (regional, account-scoped) — the ID we call;
  #   (2) the underlying foundation-model ARN in EVERY region the profile can
  #       route to (var.bedrock_geo_regions) — without these the routed call is
  #       denied even though (1) is allowed.
  bedrock_profile_arns = [
    for id in local.bedrock_profile_ids :
    "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/${id}"
  ]

  bedrock_foundation_arns = flatten([
    for region in var.bedrock_geo_regions : [
      for id in local.bedrock_model_ids :
      "arn:aws:bedrock:${region}::foundation-model/${id}"
    ]
  ])
}

# --- IAM: invoke permission on the task role ------------------------------

resource "aws_iam_role_policy" "task_bedrock" {
  name = "${var.project}-bedrock-invoke"
  role = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "InvokeNovaViaInferenceProfile"
      Effect = "Allow"
      Action = [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:Converse",
        "bedrock:ConverseStream",
      ]
      Resource = concat(local.bedrock_profile_arns, local.bedrock_foundation_arns)
    }]
  })
}

# --- Model invocation logging (metadata only) -----------------------------
#
# aws_bedrock_model_invocation_logging_configuration is account+region scoped:
# there is exactly ONE per account/region. It is owned HERE (prod stack); the
# preview stack must not also declare it or the two will fight over the same
# singleton. All *_data_delivery flags are false, so prompt and completion
# bodies never reach CloudWatch — only invocation metadata (model, token
# counts, latency, timestamps). The app emits its own metadata logs via
# structlog; this is the provider-side audit trail.

resource "aws_cloudwatch_log_group" "bedrock" {
  name              = "/aws/bedrock/${var.project}"
  retention_in_days = var.log_retention_days
}

# Role that Bedrock itself assumes to write into the log group above. The
# aws:SourceAccount condition stops any other account from using this role.
data "aws_iam_policy_document" "bedrock_logging_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "bedrock_logging" {
  name               = "${var.project}-bedrock-logging"
  assume_role_policy = data.aws_iam_policy_document.bedrock_logging_assume.json
}

resource "aws_iam_role_policy" "bedrock_logging" {
  name = "cloudwatch-logs-write"
  role = aws_iam_role.bedrock_logging.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.bedrock.arn}:*"
    }]
  })
}

resource "aws_bedrock_model_invocation_logging_configuration" "this" {
  # The write policy must exist before Bedrock validates delivery on create.
  depends_on = [aws_iam_role_policy.bedrock_logging]

  logging_config {
    cloudwatch_config {
      log_group_name = aws_cloudwatch_log_group.bedrock.name
      role_arn       = aws_iam_role.bedrock_logging.arn
    }

    embedding_data_delivery_enabled = false
    image_data_delivery_enabled     = false
    text_data_delivery_enabled      = false
  }
}

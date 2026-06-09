# Bedrock invoke permission for the preview task role.
#
# Mirrors the prod grant (modules/backend/bedrock.tf) so the per-PR preview API
# can call the same Nova models. Preview is where the LLM endpoint is actually
# exercised: prod gates protected endpoints behind 501 until real auth lands, so
# review and the live Bedrock smoke happen here.
#
# The private network path (bedrock-runtime VPC interface endpoint) is provided
# by the shared network module (modules/network/bedrock_endpoint.tf), which the
# preview stack also instantiates — no endpoint is declared here.
#
# Model-invocation logging is account+region scoped and is owned by the prod
# stack (modules/backend/bedrock.tf). It is intentionally NOT declared here to
# avoid two stacks fighting over the single per-account config.
#
# aws_caller_identity / aws_region data sources are already declared in main.tf.

locals {
  preview_bedrock_profile_ids = [
    var.bedrock_generator_model_id,
    var.bedrock_guard_model_id,
  ]
  preview_bedrock_model_ids = [for id in local.preview_bedrock_profile_ids : trimprefix(id, "eu.")]

  preview_bedrock_profile_arns = [
    for id in local.preview_bedrock_profile_ids :
    "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/${id}"
  ]
  preview_bedrock_foundation_arns = flatten([
    for region in var.bedrock_geo_regions : [
      for id in local.preview_bedrock_model_ids :
      "arn:aws:bedrock:${region}::foundation-model/${id}"
    ]
  ])
}

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
      Resource = concat(local.preview_bedrock_profile_arns, local.preview_bedrock_foundation_arns)
    }]
  })
}

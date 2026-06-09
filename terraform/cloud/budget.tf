# Bedrock monthly cost-budget alert (opt-in).
#
# AWS Budgets is account-global (not regional); one budget here watches Bedrock
# spend for the whole account. It is a backstop against runaway cost — e.g. a
# retry loop hammering Bedrock — and only NOTIFIES (email); it does not cap spend.
# The app-level rate limit (20 req/min/user, #118) is the first line of defence;
# this catches what slips past it.
#
# Opt-in by design: created only when var.cost_alert_email is set, so a CI apply
# with no email configured does not fail and no address is committed to this
# public repo. Enable by setting TF_VAR_cost_alert_email (a GitHub Actions/repo
# variable or a local tfvars).
#
# Shared-account caveat: the `Service = Amazon Bedrock` filter captures EVERY
# team's Bedrock usage on this account, so the threshold is an account-wide early
# warning, not a T2-only figure. A per-team budget would need cost-allocation
# tags activated in Billing — out of scope here.

resource "aws_budgets_budget" "bedrock_monthly" {
  count = var.cost_alert_email != "" ? 1 : 0

  name         = "${var.project}-bedrock-monthly"
  budget_type  = "COST"
  limit_amount = var.cost_alert_budget_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "Service"
    values = ["Amazon Bedrock"]
  }

  # Alert at 80% of the threshold on actual (already-incurred) spend.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.cost_alert_email]
  }
}

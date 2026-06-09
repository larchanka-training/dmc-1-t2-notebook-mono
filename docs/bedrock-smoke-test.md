# Bedrock smoke test

A live end-to-end check that the **#113** Bedrock infrastructure actually works:
the API task can invoke Amazon Nova **from a private subnet**, using **only its IAM
role**, **over the private VPC endpoint** — no public internet, no API key.

`terraform plan` proves the chart is well-formed; it cannot prove that the IAM
policy really grants the call or that the endpoint really routes. Only a live
invocation does. Run this after `apply`.

## What it proves (the three things that can break)

| Layer | If broken, you see |
| --- | --- |
| **IAM** (task-role grant, `bedrock.tf`) | `AccessDeniedException` on `bedrock:InvokeModel`/`Converse` |
| **VPC endpoint** (private corridor, `bedrock_endpoint.tf`) | connection timeout / DNS failure to `bedrock-runtime.eu-north-1.amazonaws.com` |
| **Model access / id** (Nova in `eu-north-1`) | `ValidationException: on-demand throughput isn't supported` (wrong id — must be the `eu.` Geo profile) or `AccessDeniedException` (model access not enabled) |

A clean reply with generated text means **all three** are good.

## Prerequisites

- The Bedrock infra is `apply`-ed (prod or preview). Test **preview first** — lower
  blast radius, and it is where the LLM endpoint runs (prod gates protected
  endpoints behind `501` until real auth lands).
- A running API task to exec into. In preview that is the shared main-api service
  (`jsnotes-t2-preview-main-api`); in prod it is `jsnotes-t2` / service `jsnotes-t2-api`.
  ECS Exec is enabled on both (`enable_execute_command = true`).
- `boto3` present in the API image. It ships with the backend LLM work (#117/#118);
  until then use Method B.
- Local `aws` CLI authenticated to the course account (`eu-north-1`) with
  `ecs:ExecuteCommand`. The Session Manager plugin must be installed for ECS Exec.

> **Model access — no manual step for Nova.** AWS **retired** the console *Model
> access* page (2026): Amazon-owned serverless models (Nova Lite/Micro)
> **auto-enable on first invocation**, so there is nothing to enable by hand.
> (Caveats that do **not** apply to us: Anthropic models need a one-time use-case
> form; AWS Marketplace models need a one-time enable by someone with Marketplace
> permissions.) Access is then governed entirely by IAM — i.e. our task-role
> policy. The `model access not enabled` failure mode below is therefore unlikely
> for Nova; a denial almost always means the IAM grant, not console access.

## Method A — ECS Exec into a running task (preferred)

Tests the **real** deployed task role and the **real** private endpoint.

```bash
CLUSTER=jsnotes-t2-preview          # prod: jsnotes-t2
SERVICE=jsnotes-t2-preview-main-api # prod: jsnotes-t2-api
REGION=eu-north-1

# Pick a running task of the service.
TASK=$(aws ecs list-tasks --cluster "$CLUSTER" --service-name "$SERVICE" \
  --desired-status RUNNING --region "$REGION" --query 'taskArns[0]' --output text)

# Converse against BOTH models — generator (Nova Lite) and guard (Nova Micro).
# Both are exercised: the guard model is as critical as the generator (it gates
# prompt-injection), and a single call per model proves each grant independently.
aws ecs execute-command --cluster "$CLUSTER" --task "$TASK" --container api \
  --region "$REGION" --interactive --command '/bin/sh -c "
python - <<PY
import boto3, os
c = boto3.client(\"bedrock-runtime\", region_name=os.environ.get(\"LLM_BEDROCK_REGION\", \"eu-north-1\"))
for var, default in [
    (\"LLM_BEDROCK_GENERATOR_MODEL_ID\", \"eu.amazon.nova-lite-v1:0\"),
    (\"LLM_BEDROCK_GUARD_MODEL_ID\", \"eu.amazon.nova-micro-v1:0\"),
]:
    model = os.environ.get(var, default)
    r = c.converse(
        modelId=model,
        messages=[{\"role\": \"user\", \"content\": [{\"text\": \"Reply with the single word: ok\"}]}],
        inferenceConfig={\"maxTokens\": 16},
    )
    print(\"BEDROCK_OK:\", model, \"->\", r[\"output\"][\"message\"][\"content\"][0][\"text\"])
PY
"'
```

**Pass:** output has a `BEDROCK_OK:` line for **both** the generator and the guard
model. The calls used the task's IAM role and resolved
`bedrock-runtime.eu-north-1.amazonaws.com` to the private endpoint.

## Method B — infra-only checks (no running app task, no boto3 needed)

Run before the backend image (with `boto3`) is deployed. These AWS CLI calls run
from any machine with credentials — they do **not** execute anything inside the
VPC, so they prove **IAM grant + model access + the endpoint exists with private
DNS**, but **not** the in-VPC private network path (that is Method A's job, via the
task role over the endpoint). This is exactly the layered check used to verify
#113 after the first apply.

```bash
ACCT=<account id>; REGION=eu-north-1
ROLE=arn:aws:iam::$ACCT:role/jsnotes-t2-ecs-task          # preview: jsnotes-t2-preview-ecs-task
PROFILE=arn:aws:bedrock:$REGION:$ACCT:inference-profile/eu.amazon.nova-lite-v1:0
FM=arn:aws:bedrock:$REGION::foundation-model/amazon.nova-lite-v1:0

# 1. IAM — does the task role's policy allow the call? (no spend)
#    Split by action group: InvokeModel* and Converse* can't be mixed in one call.
aws iam simulate-principal-policy --policy-source-arn "$ROLE" \
  --action-names bedrock:InvokeModel bedrock:InvokeModelWithResponseStream \
  --resource-arns "$PROFILE" "$FM" \
  --query 'EvaluationResults[].EvalDecision' --output text     # expect: allowed (x4)

# 2. Model access — are the Nova profiles active in-region?
aws bedrock list-inference-profiles --region "$REGION" \
  --query "inferenceProfileSummaries[?starts_with(inferenceProfileId,'eu.amazon.nova')].[inferenceProfileId,status]" \
  --output text                                                # expect: ... ACTIVE

# 3. Endpoint — is the private corridor up with private DNS?
aws ec2 describe-vpc-endpoints --region "$REGION" \
  --filters "Name=service-name,Values=com.amazonaws.$REGION.bedrock-runtime" \
  --query 'VpcEndpoints[].[State,PrivateDnsEnabled]' --output text   # expect: available True

# 4. The model actually answers. NOTE: this uses YOUR credentials over the public
#    Bedrock endpoint — it proves model + id + region, NOT the task role / private
#    path (those are Method A). Tiny paid call.
aws bedrock-runtime converse --region "$REGION" --model-id eu.amazon.nova-lite-v1:0 \
  --messages '[{"role":"user","content":[{"text":"Reply ok"}]}]' \
  --inference-config '{"maxTokens":16}' \
  --query 'output.message.content[0].text' --output text       # expect: ok
```

Method A remains the canonical end-to-end check (real task role, real private
endpoint); Method B is the pre-deploy, infra-only verification.

## After a pass

- Confirm the **metadata-only logging** works and leaks nothing: the
  `/aws/bedrock/jsnotes-t2` CloudWatch log group should record the invocation
  **without** the prompt or completion text (`text_data_delivery_enabled = false`).
- Record the result (date, stack, model) in the #113 PR / issue thread.

## Cleanup

Nothing to tear down: Method A is an exec into an existing task, and Method B is
read-only AWS CLI calls (check 4 is a single tiny paid invocation).

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

## Method A — ECS Exec into a running task (preferred)

Tests the **real** deployed task role and the **real** private endpoint.

```bash
CLUSTER=jsnotes-t2-preview          # prod: jsnotes-t2
SERVICE=jsnotes-t2-preview-main-api # prod: jsnotes-t2-api
REGION=eu-north-1

# Pick a running task of the service.
TASK=$(aws ecs list-tasks --cluster "$CLUSTER" --service-name "$SERVICE" \
  --desired-status RUNNING --region "$REGION" --query 'taskArns[0]' --output text)

# Run a Converse call against Nova Lite from inside the task.
aws ecs execute-command --cluster "$CLUSTER" --task "$TASK" --container api \
  --region "$REGION" --interactive --command '/bin/sh -c "
python - <<PY
import boto3, os
c = boto3.client(\"bedrock-runtime\", region_name=os.environ.get(\"LLM_BEDROCK_REGION\", \"eu-north-1\"))
r = c.converse(
    modelId=os.environ.get(\"LLM_BEDROCK_GENERATOR_MODEL_ID\", \"eu.amazon.nova-lite-v1:0\"),
    messages=[{\"role\": \"user\", \"content\": [{\"text\": \"Reply with the single word: ok\"}]}],
    inferenceConfig={\"maxTokens\": 16},
)
print(\"BEDROCK_OK:\", r[\"output\"][\"message\"][\"content\"][0][\"text\"])
PY
"'
```

**Pass:** output contains `BEDROCK_OK: ok` (or similar). The call used the task's
IAM role and resolved `bedrock-runtime.eu-north-1.amazonaws.com` to the private
endpoint. Repeat with `LLM_BEDROCK_GUARD_MODEL_ID` (`eu.amazon.nova-micro-v1:0`) to
confirm the guard model too.

## Method B — one-off run-task (before boto3 is in the image)

Pulls the public AWS CLI image and calls Bedrock directly. The public-ECR pull
needs egress, so this works in **prod** (NAT) but not in the no-NAT preview VPC —
use Method A for preview.

```bash
REGION=eu-north-1
SUBNET=<a private subnet id from `terraform -chdir=terraform/cloud output`>
SG=<the ecs security group id>

aws ecs run-task --region "$REGION" --launch-type FARGATE \
  --cluster jsnotes-t2 \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG],assignPublicIp=DISABLED}" \
  --overrides '{"containerOverrides":[{"name":"api","command":[
    "aws","bedrock-runtime","converse",
    "--model-id","eu.amazon.nova-lite-v1:0",
    "--messages","[{\"role\":\"user\",\"content\":[{\"text\":\"Reply ok\"}]}]",
    "--region","eu-north-1"]}]}' \
  --task-definition <a task def that uses the bedrock task role>
```

Then read the task's CloudWatch logs for the model reply. (Method B is a fallback;
Method A is the canonical check.)

## After a pass

- Confirm the **metadata-only logging** works and leaks nothing: the
  `/aws/bedrock/jsnotes-t2` CloudWatch log group should record the invocation
  **without** the prompt or completion text (`text_data_delivery_enabled = false`).
- Record the result (date, stack, model) in the #113 PR / issue thread.

## Cleanup

Method A leaves nothing behind. Method B's task is one-off and exits on its own;
no teardown needed.

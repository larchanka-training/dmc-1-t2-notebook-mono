# LLM provider smoke test

This runbook verifies that the deployed API can invoke the configured backend
LLM provider without exposing provider keys to the browser or logs.

The endpoint under test is:

```text
POST /api/v1/llm/generate
```

## Scope

Use this before switching production traffic to a new provider or model.

Current provider options:

- `LLM_PROVIDER=bedrock`
- `LLM_PROVIDER=openrouter`

OpenRouter must stay behind a non-empty `LLM_ALLOWED_EMAILS` developer allowlist
until the live smoke result is recorded and reviewed.

## Preconditions

- The target environment has a real user account created through the normal
  email OTP login flow.
- The account email is included in `LLM_ALLOWED_EMAILS` when the allowlist is
  enabled.
- Runtime secrets live only in the server `.env.prod`; do not put keys in
  GitHub repository variables, PR bodies, screenshots, or client-side `VITE_*`
  variables.

Provider-specific requirements:

| Provider | Required runtime settings |
| --- | --- |
| `bedrock` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `LLM_BEDROCK_REGION`, `LLM_BEDROCK_GUARD_MODEL_ID`, `LLM_BEDROCK_GENERATOR_MODEL_ID` |
| `openrouter` | `LLM_OPENROUTER_API_KEY`, `LLM_OPENROUTER_GUARD_MODEL_ID`, `LLM_OPENROUTER_GENERATOR_MODEL_ID`, `LLM_ALLOWED_EMAILS` |

## Procedure

1. Deploy the target image tag with the intended `.env.prod` values.
2. Check that the API is healthy:

   ```bash
   curl -fsS https://jsnb.org/api/v1/health
   ```

3. Sign in through the UI as an allowlisted developer account and capture the
   access token from the authenticated API request headers in DevTools.

4. Send one minimal generation request:

   ```bash
   curl -fsS https://jsnb.org/api/v1/llm/generate \
     -H "Authorization: Bearer $ACCESS_TOKEN" \
     -H "Content-Type: application/json" \
     --data '{
       "prompt": "Return JavaScript that prints the string ok.",
       "context": []
     }'
   ```

5. Verify the response:

   - HTTP status is `200`.
   - `content` is present and non-empty.
   - `model` matches the intended provider model id.
   - `tokens.prompt` and `tokens.completion` are numeric.

6. Verify the server logs:

   - no API key appears;
   - no raw prompt appears;
   - no raw completion appears;
   - provider logs contain only metadata such as provider/model/status/token
     counts/request id.

7. Verify the allowlist guard with a non-allowlisted signed-in account:

   ```bash
   curl -i https://jsnb.org/api/v1/llm/generate \
     -H "Authorization: Bearer $NON_ALLOWED_ACCESS_TOKEN" \
     -H "Content-Type: application/json" \
     --data '{
       "prompt": "Return JavaScript that prints the string ok.",
       "context": []
     }'
   ```

   Expected: `403`.

## Evidence

Record the result in the rollout evidence for the current phase:

- provider and model ids;
- image tag;
- UTC timestamp;
- request id;
- HTTP status;
- token metadata;
- allowlist negative check result;
- confirmation that logs did not contain keys, raw prompt, or raw completion.

Do not record the provider API key, access token, raw prompt, or raw completion.

## Rollback

To stop OpenRouter traffic without changing images:

```bash
LLM_PROVIDER=bedrock
```

Then redeploy/restart the API with the previous Bedrock credentials still in
`.env.prod`.

import { test } from '../fixtures/index'

/**
 * AT-LLM-01..07 (LLM code generation) — NOT AUTOMATABLE as written.
 *
 * KNOWN LIMITATION (release-report §Known limitations): the implemented UI path
 * generates code fully IN-BROWSER via WebLLM (@mlc-ai/web-llm) — the user loads
 * a model in the NotebookLlmBar and the "Generate code" button on a markdown
 * cell runs local inference. It does NOT call the backend `/llm/generate`
 * proxy, so the roadmap's fallback-chain specs (AT-LLM-02 backend, AT-LLM-03
 * OpenAI, AT-LLM-04 all-fail) and the `mockWasmLlm` happy path (AT-LLM-01) do
 * not match reality. End-to-end browser inference also requires downloading a
 * multi-hundred-MB model — not viable in a local/CI E2E run.
 *
 * The backend `/llm/generate` endpoint EXISTS and is covered at the API level
 * (autotests/api/tests/test_llm.py: auth, validation, rate-limit shape). Real
 * generation there needs Amazon Bedrock credentials and is out of local scope.
 *
 * Verified against ui@0082a09 (NotebookLlmBar / codeGenerator) and api@8439b84.
 */
test.describe('LLM generation @blocked', () => {
  test.skip('AT-LLM-01 WASM happy path — UI uses in-browser WebLLM, not mockable proxy', () => {})
  test.skip('AT-LLM-02 fallback to backend — UI does not call /llm/generate', () => {})
  test.skip('AT-LLM-03 fallback to OpenAI — not in implemented path', () => {})
  test.skip('AT-LLM-04 all levels fail — not in implemented path', () => {})
})

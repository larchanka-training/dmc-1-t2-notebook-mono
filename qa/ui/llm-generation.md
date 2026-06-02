# UI Test Cases — LLM Code Generation

**Feature:** AI code generation (WASM → Backend → OpenAI fallback chain)  
**Stack:** React / TypeScript, WASM LLM  
**Priority scope:** Smoke, Regression, Edge

---

## TC-UI-LLM-01 — WASM LLM generates code (happy path)

**Priority:** Smoke  
**Related scenario:** L-01, L-07

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open a notebook, locate LLM prompt panel | Prompt field visible |
| 2 | Enter a valid prompt (e.g. "Write a function that adds two numbers") | — |
| 3 | Click "Generate" | Loading indicator shown |
| 4 | Wait for generation | Code inserted into editor |
| 5 | Check network tab | No request to `/llm/generate` (WASM handled it) |
| 6 | Check prompt panel | Cleared or hidden after insertion |

**Pass criteria:** Code in editor, no network call, prompt cleared  
**Fail criteria:** Editor unchanged, network call made unexpectedly, app hangs

---

## TC-UI-LLM-02 — Fallback to backend LLM

**Priority:** Regression  
**Related scenario:** L-02

| Step | Action | Expected Result |
|---|---|---|
| 1 | Simulate WASM failure (disable WASM or use mocked response) | — |
| 2 | Enter a prompt, click "Generate" | — |
| 3 | Check network tab | Request to `POST /llm/generate` made |
| 4 | Check editor | Code from backend response inserted |
| 5 | Check UI | No error message shown to user during process |

**Pass criteria:** Code inserted, no error shown, backend called exactly once  
**Fail criteria:** Error shown to user, editor unchanged, multiple requests

---

## TC-UI-LLM-03 — Fallback to OpenAI

**Priority:** Regression  
**Related scenario:** L-03

| Step | Action | Expected Result |
|---|---|---|
| 1 | Simulate WASM failure and backend LLM failure | — |
| 2 | Enter a prompt, click "Generate" | — |
| 3 | Wait for generation | Code inserted into editor |
| 4 | Check UI | Optional: notification that OpenAI was used |
| 5 | Check editor | Code is valid and inserted |

**Pass criteria:** Code inserted, fallback transparent to user  
**Fail criteria:** Error shown, editor unchanged, app hangs

---

## TC-UI-LLM-04 — All LLM tiers unavailable

**Priority:** Regression  
**Related scenario:** L-04

| Step | Action | Expected Result |
|---|---|---|
| 1 | Simulate failure of WASM + backend + OpenAI | — |
| 2 | Enter a prompt, click "Generate" | — |
| 3 | Wait for response | Clear error message displayed |
| 4 | Check editor | Content unchanged |
| 5 | Check Generate button | Button active again (not stuck loading) |

**Pass criteria:** Error message shown, editor untouched, button re-enabled  
**Fail criteria:** Silent failure, partial code inserted, button stuck in loading state

---

## TC-UI-LLM-05 — Empty prompt blocked

**Priority:** Regression  
**Related scenario:** L-05

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open LLM prompt panel | Prompt field empty |
| 2 | Do not type anything | — |
| 3 | Click "Generate" (or observe button state) | Button is disabled OR click does nothing |
| 4 | Check network tab | No request sent |

**Pass criteria:** Generate blocked with empty input  
**Fail criteria:** Request sent with empty prompt, 422 error visible to user

---

## TC-UI-LLM-06 — Prompt exceeds character limit

**Priority:** Regression  
**Related scenario:** L-06

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open LLM prompt panel | Character counter visible |
| 2 | Paste text > max character limit (e.g. 2001 chars) | — |
| 3 | Check counter | Counter turns red, shows over-limit count |
| 4 | Check Generate button | Disabled |
| 5 | Check network tab | No request sent |

**Pass criteria:** Counter red, button disabled, no request  
**Fail criteria:** Request sent anyway, counter not shown, no visual feedback

---

## TC-UI-LLM-07 — Loading state while WASM initializes

**Priority:** Edge  
**Related scenario:** L-09

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open notebook (WASM LLM not yet loaded) | — |
| 2 | Immediately enter a prompt and click "Generate" | Loading indicator shown ("Loading model...") |
| 3 | Wait for WASM to finish loading | Code inserted without re-clicking |
| 4 | Check UI | Loading indicator gone, result visible |

**Pass criteria:** Loading state shown, result appears automatically after load  
**Fail criteria:** Error shown before WASM loads, user must click again, spinner never resolves

---

## TC-UI-LLM-08 — Browser without WASM support

**Priority:** Edge  
**Related scenario:** L-10

| Step | Action | Expected Result |
|---|---|---|
| 1 | Use browser without WebAssembly support (or simulate via DevTools) | — |
| 2 | Enter a prompt, click "Generate" | — |
| 3 | Check network tab | Request goes to backend `/llm/generate` |
| 4 | Check UI | No WASM-related error shown |
| 5 | Check editor | Code inserted successfully |

**Pass criteria:** Transparent fallback to backend, no WASM error visible  
**Fail criteria:** WASM error exposed to user, editor unchanged, no fallback attempted

---

## TC-UI-LLM-09 — Generation in progress — tab closed

**Priority:** Edge  
**Related scenario:** L-08

| Step | Action | Expected Result |
|---|---|---|
| 1 | Start code generation (slow prompt) | Loading indicator shown |
| 2 | Close and reopen the tab before generation completes | — |
| 3 | Check editor | No partial/incomplete code inserted |
| 4 | Check app state | Clean state, no stuck loading indicator |

**Pass criteria:** Editor clean, no partial code, app in clean state  
**Fail criteria:** Partial code in editor, loading spinner stuck, app errors on reopen

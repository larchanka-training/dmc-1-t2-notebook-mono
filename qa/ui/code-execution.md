# UI Test Cases — Code Execution (Sandbox)

**Feature:** JS code execution in browser sandbox  
**Stack:** React / TypeScript, iframe / Web Worker sandbox  
**Priority scope:** Smoke, Regression, Edge

---

## TC-UI-EX-01 — Basic console.log output

**Priority:** Smoke  
**Related scenario:** X-01

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open a notebook | Editor visible |
| 2 | Enter `console.log("hello")` | — |
| 3 | Click "Run" | Output panel opens |
| 4 | Check output panel | Contains string `hello` |
| 5 | Open browser DevTools console | No uncaught errors |

**Pass criteria:** `hello` in output, no console errors  
**Fail criteria:** Output empty, wrong value, panel doesn't appear

---

## TC-UI-EX-02 — Multiple values in one run

**Priority:** Regression

| Step | Action | Expected Result |
|---|---|---|
| 1 | Enter: `console.log(1); console.log("a"); console.log(true)` | — |
| 2 | Click "Run" | — |
| 3 | Check output panel | Shows `1`, `a`, `true` in order |

**Pass criteria:** All values displayed in correct order  
**Fail criteria:** Values missing, wrong order, only last value shown

---

## TC-UI-EX-03 — Runtime error display

**Priority:** Regression  
**Related scenario:** X-02 (adapted)

| Step | Action | Expected Result |
|---|---|---|
| 1 | Enter `null.property` | — |
| 2 | Click "Run" | — |
| 3 | Check output panel | `TypeError: Cannot read properties of null` shown |
| 4 | Verify app state | Run button still available, app not crashed |

**Pass criteria:** TypeError displayed, app functional  
**Fail criteria:** Blank output, app crash, browser tab frozen

---

## TC-UI-EX-04 — Syntax error caught before execution

**Priority:** Regression  
**Related scenario:** X-04

| Step | Action | Expected Result |
|---|---|---|
| 1 | Enter `const x = {` (incomplete object) | — |
| 2 | Click "Run" | — |
| 3 | Check output | `SyntaxError` shown before any execution |
| 4 | Verify app state | Run button still available |

**Pass criteria:** SyntaxError shown immediately, no execution attempted  
**Fail criteria:** Code partially executed, no error shown, app crashes

---

## TC-UI-EX-05 — Infinite loop terminated by timeout

**Priority:** Regression  
**Related scenario:** X-02

| Step | Action | Expected Result |
|---|---|---|
| 1 | Enter `while(true) {}` | — |
| 2 | Click "Run" | — |
| 3 | Wait for sandbox timeout (per documented limit) | Execution aborted |
| 4 | Check output panel | Timeout/abort message shown |
| 5 | Interact with the page | Page remains responsive (click other elements) |

**Pass criteria:** Timeout message shown, page responsive  
**Fail criteria:** Browser tab hangs, no timeout, page becomes unresponsive

---

## TC-UI-EX-06 — fetch() behavior per sandbox policy

**Priority:** Edge  
**Related scenario:** X-03

| Step | Action | Expected Result |
|---|---|---|
| 1 | Enter `fetch("https://example.com").then(r => console.log(r.status)).catch(e => console.log("blocked:", e.message))` | — |
| 2 | Click "Run" | — |
| 3 | Check output | Either: HTTP status shown (fetch allowed) OR: clear "blocked" message (fetch blocked) |
| 4 | Compare with documented sandbox policy | Behavior matches documentation |

**Pass criteria:** Behavior is clear and matches documented policy  
**Fail criteria:** Unhandled exception, blank output, behavior contradicts documentation

---

## TC-UI-EX-07 — Output cleared between runs

**Priority:** Regression

| Step | Action | Expected Result |
|---|---|---|
| 1 | Enter `console.log("first")`, click "Run" | Output: `first` |
| 2 | Clear editor, enter `console.log("second")`, click "Run" | — |
| 3 | Check output panel | Shows only `second`, not `first` |

**Pass criteria:** Output from previous run cleared  
**Fail criteria:** Outputs accumulate across runs without clear separation

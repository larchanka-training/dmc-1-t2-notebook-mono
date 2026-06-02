# UI Test Cases — Notebook Editor

**Feature:** Notebook CRUD and editor interactions  
**Stack:** React / TypeScript  
**Priority scope:** Smoke, Regression

---

## TC-UI-NB-01 — Create a new notebook

**Priority:** Smoke  
**Related scenario:** E-01

| Step | Action | Expected Result |
|---|---|---|
| 1 | Log in, open dashboard | Sidebar visible |
| 2 | Click "Create notebook" button | — |
| 3 | Observe editor | Empty editor opens |
| 4 | Check URL | Contains new notebook id |
| 5 | Check sidebar | Default title present |
| 6 | Wait 2 seconds | Notebook appears in sidebar list |

**Pass criteria:** Empty editor with id in URL, default title in sidebar  
**Fail criteria:** Editor doesn't open, no id in URL, sidebar not updated

---

## TC-UI-NB-02 — Write code and run it

**Priority:** Smoke  
**Related scenario:** E-02

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open a notebook | Editor visible |
| 2 | Type `console.log("hello world")` | Code appears in editor |
| 3 | Click "Run" | Output panel appears |
| 4 | Check output | "hello world" shown in output panel |
| 5 | Check browser console | No uncaught errors |

**Pass criteria:** Output panel shows correct result, no errors  
**Fail criteria:** Output empty, wrong value, app crashes

---

## TC-UI-NB-03 — Run code with a runtime error

**Priority:** Regression  
**Related scenario:** E-03

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open a notebook | Editor visible |
| 2 | Enter `undefinedFunction()` | — |
| 3 | Click "Run" | — |
| 4 | Check output panel | Error message shown (e.g. `ReferenceError: undefinedFunction is not defined`) |
| 5 | Check app state | App does not crash, run button still available |

**Pass criteria:** Error displayed in output panel, app remains functional  
**Fail criteria:** App crashes, blank output, browser tab freezes

---

## TC-UI-NB-04 — Manual save and persistence

**Priority:** Regression  
**Related scenario:** E-04

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open a notebook, type some code | — |
| 2 | Click save button | "Saved" toast notification appears |
| 3 | Wait for toast to disappear | — |
| 4 | Reload the page (`F5`) | — |
| 5 | Check editor content | Same code is present |

**Pass criteria:** Toast shown, code persists after reload  
**Fail criteria:** No toast, code lost on reload, save button unresponsive

---

## TC-UI-NB-05 — Rename a notebook

**Priority:** Regression  
**Related scenario:** E-05

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open a notebook | Default title shown |
| 2 | Click on the title field | Title becomes editable |
| 3 | Clear and type new name "My Test Notebook" | — |
| 4 | Confirm (press Enter or click away) | New title shown in editor header |
| 5 | Check sidebar | New title reflected in sidebar |
| 6 | Check browser tab | Tab title updated |
| 7 | Reload page | New name still shown |

**Pass criteria:** Title updated in all locations and persists  
**Fail criteria:** Title reverts, sidebar not updated, browser tab not updated

---

## TC-UI-NB-06 — Delete a notebook

**Priority:** Regression  
**Related scenario:** E-06

| Step | Action | Expected Result |
|---|---|---|
| 1 | Create two notebooks | Both shown in sidebar |
| 2 | Open one and delete it via UI | Confirmation dialog shown |
| 3 | Confirm deletion | — |
| 4 | Check URL | Redirected to dashboard or other notebook |
| 5 | Check sidebar | Deleted notebook no longer listed |

**Pass criteria:** Notebook removed from sidebar, redirect occurs  
**Fail criteria:** Notebook still in sidebar, wrong redirect, delete confirmation not shown

---

## TC-UI-NB-07 — Navigate between multiple notebooks

**Priority:** Regression  
**Related scenario:** E-07

| Step | Action | Expected Result |
|---|---|---|
| 1 | Create 3 notebooks with distinct code | All shown in sidebar |
| 2 | Click notebook 1 | Editor shows notebook 1 content |
| 3 | Click notebook 2 | Editor switches to notebook 2 content |
| 4 | Click notebook 3 | Editor switches to notebook 3 content |
| 5 | Click notebook 1 again | Editor shows notebook 1 content, no state bleed |

**Pass criteria:** Editor content matches selected notebook each time  
**Fail criteria:** Wrong content shown, content from previous notebook leaks, URL not updated

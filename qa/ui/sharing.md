# UI Test Cases — Sharing

**Feature:** Notebook share link generation and guest access  
**Stack:** React / TypeScript  
**Priority scope:** Smoke, Regression, Edge

---

## TC-UI-SH-01 — Generate a share link

**Priority:** Smoke  
**Related scenario:** S-01

| Step | Action | Expected Result |
|---|---|---|
| 1 | Log in, open a notebook with code | Editor visible |
| 2 | Click "Share" button | Share panel opens |
| 3 | Click "Generate link" | Unique URL generated |
| 4 | Check URL format | Contains a unique id or hash |
| 5 | Check UI | Copy button visible and functional |

**Pass criteria:** Unique share URL generated, copy button works  
**Fail criteria:** No URL generated, same URL for every notebook, copy fails

---

## TC-UI-SH-02 — Guest opens share link in read-only mode

**Priority:** Smoke  
**Related scenario:** S-02

| Step | Action | Expected Result |
|---|---|---|
| 1 | Generate a share link for a notebook | URL obtained |
| 2 | Open URL in a private/incognito window (no JWT) | — |
| 3 | Observe page | Notebook displayed with correct content |
| 4 | Check editor state | Edit controls absent or disabled |
| 5 | Check save/rename buttons | Not present or visually disabled |

**Pass criteria:** Content visible, no editing possible  
**Fail criteria:** Page shows 404, edit allowed, content from wrong notebook shown

---

## TC-UI-SH-03 — Guest runs code in a shared notebook

**Priority:** Regression  
**Related scenario:** S-03

| Step | Action | Expected Result |
|---|---|---|
| 1 | Create notebook with `console.log(42)`, generate share link | — |
| 2 | Open share link as a guest (no JWT) | Notebook displayed |
| 3 | Click "Run" button | Execution occurs |
| 4 | Check output panel | Shows `42` |
| 5 | Check owner's notebook | Code in editor unchanged, output not saved |

**Pass criteria:** Execution works for guest, owner data not modified  
**Fail criteria:** Run button missing for guest, wrong output, owner notebook modified

---

## TC-UI-SH-04 — Revoke a share link

**Priority:** Regression  
**Related scenario:** S-04

| Step | Action | Expected Result |
|---|---|---|
| 1 | Generate share link, save the URL | — |
| 2 | Click "Revoke" in share panel | Confirmation shown |
| 3 | Confirm revocation | Share panel updates — link marked as revoked |
| 4 | Open saved URL in guest context | 404 or "not found" message shown |
| 5 | Check page | Notebook content not visible |

**Pass criteria:** Link revoked, guest gets 404 or not-found  
**Fail criteria:** Link still works after revoke, guest can still see content

---

## TC-UI-SH-05 — Share link for a deleted notebook

**Priority:** Edge  
**Related scenario:** S-05

| Step | Action | Expected Result |
|---|---|---|
| 1 | Create a notebook, generate share link | — |
| 2 | Delete the notebook | Redirected away |
| 3 | Open share link in guest context | — |
| 4 | Check response | 404 or "notebook not found" UI message |
| 5 | Check for JS errors | No uncaught exceptions or blank screen |

**Pass criteria:** Clear 404 message, no crash  
**Fail criteria:** Blank white screen, JS errors in console, content from another notebook shown

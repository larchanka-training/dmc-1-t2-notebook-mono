# API Test Cases — Notebooks

**Feature:** Notebook CRUD, sharing, sync  
**Base URL:** `https://api.notebook.com`  
**Tool:** pytest + httpx / Bruno  
**Auth:** All requests use `Authorization: Bearer <valid_jwt>` unless stated otherwise  
**Priority scope:** Smoke, Regression, Edge

---

## TC-API-NB-01 — List notebooks (authenticated)

**Priority:** Smoke  
**Related scenario:** R-05  
**Endpoint:** `GET /notebooks`

| Field | Value |
|---|---|
| Headers | `Authorization: Bearer <jwt>` |
| Expected status | `200` |
| Expected body | Array of notebook objects (empty array if none exist) |
| Schema | Each item: `id`, `title`, `created_at`, `updated_at` |

**Pass criteria:** 200 with array  
**Fail criteria:** Non-array body, missing required fields, 500

---

## TC-API-NB-02 — List notebooks (unauthenticated)

**Priority:** Regression  
**Endpoint:** `GET /notebooks`

| Field | Value |
|---|---|
| Headers | None |
| Expected status | `401` |

**Pass criteria:** 401 returned  
**Fail criteria:** 200, data returned without auth

---

## TC-API-NB-03 — Create a notebook

**Priority:** Smoke  
**Related scenario:** R-07  
**Endpoint:** `POST /notebooks`

| Field | Value |
|---|---|
| Request body | `{ "title": "My Notebook" }` |
| Expected status | `201` |
| Expected body | `{ "id": "...", "title": "My Notebook", "created_at": "..." }` |

**Pass criteria:** 201 with new notebook object  
**Fail criteria:** 200, 422, 500, id missing from response

---

## TC-API-NB-04 — Create notebook with missing title

**Priority:** Regression  
**Endpoint:** `POST /notebooks`

| Field | Value |
|---|---|
| Request body | `{}` |
| Expected status | `201` (default title assigned) OR `422` (title required) |

**Pass criteria:** Either 201 with default title or 422 with clear error  
**Fail criteria:** 500, notebook created with null title

---

## TC-API-NB-05 — Get a specific notebook

**Priority:** Regression  
**Endpoint:** `GET /notebooks/:id`

| Field | Value |
|---|---|
| Precondition | Notebook exists for this user |
| Expected status | `200` |
| Expected body | Full notebook object including cells |

**Pass criteria:** 200 with correct notebook data  
**Fail criteria:** 404 for own notebook, wrong notebook returned

---

## TC-API-NB-06 — Get another user's notebook (forbidden)

**Priority:** Regression  
**Endpoint:** `GET /notebooks/:id`

| Field | Value |
|---|---|
| Precondition | Notebook belongs to different user |
| Expected status | `403` or `404` |

**Pass criteria:** 403 or 404, no data exposed  
**Fail criteria:** 200 with other user's data

---

## TC-API-NB-07 — Update a notebook

**Priority:** Regression  
**Endpoint:** `PATCH /notebooks/:id` or `PUT /notebooks/:id`

| Field | Value |
|---|---|
| Request body | `{ "title": "Updated Title" }` |
| Expected status | `200` |
| Expected body | Updated notebook object |

**Pass criteria:** 200 with updated title  
**Fail criteria:** 404, 422, title not updated in response

---

## TC-API-NB-08 — Delete a notebook (own)

**Priority:** Regression  
**Endpoint:** `DELETE /notebooks/:id`

| Field | Value |
|---|---|
| Precondition | Notebook belongs to current user |
| Expected status | `204` or `200` |

**Pass criteria:** 204/200 returned, notebook no longer retrievable  
**Fail criteria:** 404, notebook still accessible after delete

---

## TC-API-NB-09 — Delete another user's notebook (forbidden)

**Priority:** Regression  
**Related scenario:** R-08  
**Endpoint:** `DELETE /notebooks/:id`

| Field | Value |
|---|---|
| Precondition | Notebook belongs to different user |
| Expected status | `403` |

**Pass criteria:** 403 returned, notebook not deleted  
**Fail criteria:** 200, 204 — notebook deleted

---

## TC-API-NB-10 — Get notebook by non-existent id

**Priority:** Regression  
**Endpoint:** `GET /notebooks/non-existent-id`

| Field | Value |
|---|---|
| Expected status | `404` |
| Expected body | Error message |

**Pass criteria:** 404 with error message  
**Fail criteria:** 500, 200 with null, server crash

---

## TC-API-NB-11 — Get public share link

**Priority:** Smoke  
**Related scenario:** R-09  
**Endpoint:** `GET /notebooks/:id/share`

| Field | Value |
|---|---|
| Headers | None (no JWT — public endpoint) |
| Precondition | Notebook share link generated |
| Expected status | `200` |
| Expected body | Notebook data (read-only fields) |

**Pass criteria:** 200 without authentication  
**Fail criteria:** 401, data not returned for public link

---

## TC-API-NB-12 — Get share link for revoked notebook

**Priority:** Edge  
**Endpoint:** `GET /notebooks/:id/share`

| Field | Value |
|---|---|
| Precondition | Share link was revoked |
| Expected status | `404` |

**Pass criteria:** 404 returned  
**Fail criteria:** 200, data still accessible

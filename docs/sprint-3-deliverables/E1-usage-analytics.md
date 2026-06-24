# Engineer #1 — Usage Analytics

## Objective

Define and document product analytics for the key notebook and AI workflows.

## Required Tracking

- notebook creation
- cell execution
- AI requests
- execution errors

## Event Inventory

| Event name | Trigger | Properties | Source | Destination |
|---|---|---|---|---|
| notebook_created | | | | |
| cell_executed | | | | |
| ai_request_sent | | | | |
| execution_error | | | | |

## Event Schema Notes

### Common fields

- timestamp
- user identifier or anonymous session identifier
- notebook identifier
- environment
- app version

### Per-event fields

#### `notebook_created`

- fields:
- success criteria:

#### `cell_executed`

- fields:
- success criteria:

#### `ai_request_sent`

- fields:
- success criteria:

#### `execution_error`

- fields:
- success criteria:

## Dashboard Plan

| Widget | Metric | Audience | Why it matters |
|---|---|---|---|
| | | | |

## Implementation Notes

- frontend instrumentation:
- backend instrumentation:
- CloudWatch / analytics storage:
- privacy considerations:

## Validation

- How events will be verified:
- Expected sample data:
- Known gaps:

## Deliverable Status

- Events implemented:
- Dashboard implemented:
- Remaining work:

# AI Code Generation — Test Cases

**Feature:** LLM code generation via prompt panel (`POST /api/llm/generate` or WASM fallback)  
**Context:** The LLM backend is not yet connected. These test cases prepare prompts and validation criteria for future manual and automated testing once the integration is live.  
**System prompt in effect (per `docs/requirements.md` §3.3):**
```
You are an assistant that writes clean JavaScript code.
Return ONLY the code, with no explanations or markdown blocks.
The code must work in a browser sandbox environment without a Python API.
```
**Total test cases:** 40  
**Coverage:** function generation (12), class generation (8), React component generation (9), LLM response behavior — empty / error / timeout (11)

---

## Priority legend

| Priority | When run |
|---|---|
| **Smoke** | Every PR |
| **Regression** | Nightly + merge to `main` |
| **Edge** | Nightly, separate schedule acceptable |

---

## Category 1 — Function Generation

### TC-AI-F-01 — Simple utility function

**Priority:** Smoke

**Prompt:**
```
Write a function that adds two numbers and returns the result.
```

**Expected LLM behavior:**
- Returns a named function (e.g. `function add(a, b)` or `const add = (a, b) =>`)
- No markdown fences (` ``` `)
- No prose explanation
- Code is syntactically valid JavaScript

**Pass criteria:** Code inserted into editor, parseable by `new Function(code)`, no markdown fences  
**Fail criteria:** Explanation text included, fences present, editor unchanged

---

### TC-AI-F-02 — Function with multiple parameters and default values

**Priority:** Regression

**Prompt:**
```
Write a function formatName that takes firstName, lastName, and an optional separator (default is a space) and returns the full name as a string.
```

**Expected LLM behavior:**
- Uses default parameter syntax: `separator = ' '`
- Returns a string concatenation or template literal
- Handles edge cases internally (optional)

**Pass criteria:** Function uses default parameter, returns string, syntactically valid  
**Fail criteria:** No default value, uses `arguments` object, missing return statement

---

### TC-AI-F-03 — Async function with `await`

**Priority:** Regression

**Prompt:**
```
Write an async function fetchUserData(userId) that fetches JSON from /api/users/{userId} using fetch() and returns the parsed response body.
```

**Expected LLM behavior:**
- `async function` or `const fetchUserData = async`
- Uses `await fetch(...)` and `await response.json()`
- No try/catch required (happy path only)

**Pass criteria:** `async` keyword present, `await` used, returns parsed body  
**Fail criteria:** Uses `.then()` chaining only, missing `async`, no `await`

---

### TC-AI-F-04 — Function with error handling

**Priority:** Regression

**Prompt:**
```
Write a function safeDivide(a, b) that returns the result of a / b. If b is zero, throw an Error with the message "Division by zero".
```

**Expected LLM behavior:**
- Explicit `if (b === 0)` or `if (!b)` guard
- `throw new Error("Division by zero")`
- Otherwise returns `a / b`

**Pass criteria:** Guard present, `throw new Error(...)` used, message matches or semantically equivalent  
**Fail criteria:** No guard, returns `Infinity`, guard present but wrong error type

---

### TC-AI-F-05 — Recursive function

**Priority:** Regression

**Prompt:**
```
Write a recursive function fibonacci(n) that returns the nth Fibonacci number. Use memoization to avoid redundant calculations.
```

**Expected LLM behavior:**
- Recursive calls to `fibonacci`
- Memoization via a `Map`, plain object, or closure
- Base cases for `n <= 1`

**Pass criteria:** Recursion present, memoization present, base cases handled  
**Fail criteria:** Iterative solution without recursion, no memoization, infinite recursion risk for `n=0`

---

### TC-AI-F-06 — Higher-order function

**Priority:** Regression

**Prompt:**
```
Write a function debounce(fn, delay) that returns a debounced version of fn. The debounced function should postpone execution until after delay milliseconds have passed since the last call.
```

**Expected LLM behavior:**
- Returns a new function (closure)
- Uses `setTimeout` and `clearTimeout`
- Preserves `this` context and arguments

**Pass criteria:** Returns a function, uses `setTimeout`/`clearTimeout`, valid JS closure  
**Fail criteria:** Returns non-function value, uses `setInterval`, no timer cleanup

---

### TC-AI-F-07 — Array transformation function

**Priority:** Regression

**Prompt:**
```
Write a function groupBy(array, keyFn) that groups an array of objects by the value returned by keyFn. Return an object where keys are group names and values are arrays.
```

**Expected LLM behavior:**
- Uses `reduce` or a loop to accumulate groups
- Handles empty array (returns `{}`)
- Uses the return value of `keyFn(item)` as the key

**Pass criteria:** Returns a plain object, groups correctly by key, valid for empty input  
**Fail criteria:** Returns an array, hardcoded key, crashes on empty array

---

### TC-AI-F-08 — Generator function

**Priority:** Edge

**Prompt:**
```
Write a generator function range(start, end, step) that yields numbers from start to end (exclusive) with the given step.
```

**Expected LLM behavior:**
- Uses `function*` syntax
- Uses `yield` inside a loop
- Handles `step` parameter (default 1 acceptable)

**Pass criteria:** `function*` syntax, `yield` present, valid iteration  
**Fail criteria:** Returns an array, missing `*`, no `yield`

---

### TC-AI-F-09 — Pure functional style (no mutations)

**Priority:** Edge

**Prompt:**
```
Write a function deepClone(obj) that returns a deep copy of a plain JavaScript object (no Date, RegExp, or class instances needed). Do not mutate the input.
```

**Expected LLM behavior:**
- Handles nested objects recursively
- Handles arrays
- Does not use `JSON.parse(JSON.stringify(obj))` — or if it does, that is acceptable for a plain-object scope

**Pass criteria:** Returns a new object, does not mutate input, handles nesting  
**Fail criteria:** Returns the same reference, shallow copy only, crashes on `null`

---

### TC-AI-F-10 — Function with TypeScript-style JSDoc

**Priority:** Edge

**Prompt:**
```
Write a JavaScript function sortByKey(array, key, direction) where direction is "asc" or "desc". Add JSDoc comments with @param and @returns tags.
```

**Expected LLM behavior:**
- JavaScript function (not TypeScript)
- JSDoc block with `@param` and `@returns`
- Sorts array without mutating or returns sorted copy

**Pass criteria:** JSDoc present, valid sort logic, no TypeScript syntax  
**Fail criteria:** TypeScript types in function signature, no JSDoc, mutates input without note

---

### TC-AI-F-11 — Curried function

**Priority:** Edge

**Prompt:**
```
Write a curried function multiply that can be called as multiply(2)(3) and returns 6.
```

**Expected LLM behavior:**
- Outer function returns an inner function
- Inner function multiplies the two arguments

**Pass criteria:** Returns a function from the outer call, multiplication correct  
**Fail criteria:** `multiply(2, 3)` instead of currying, returns a value not a function

---

### TC-AI-F-12 — Function chaining / fluent API

**Priority:** Edge

**Prompt:**
```
Write a function createPipeline(...fns) that takes a list of functions and returns a new function that passes its argument through each function in sequence, returning the final result.
```

**Expected LLM behavior:**
- Uses `reduce` or a loop over `fns`
- Returns a single-argument function
- Composes left-to-right

**Pass criteria:** Returns a function, reduces over `fns`, correct composition order  
**Fail criteria:** Executes functions immediately, reverses order, crashes with zero functions

---

## Category 2 — Class Generation

### TC-AI-C-01 — Simple class with constructor and methods

**Priority:** Smoke

**Prompt:**
```
Write a JavaScript class BankAccount with a constructor that takes an owner name and initial balance. Add methods deposit(amount), withdraw(amount), and getBalance(). Throw an error if a withdrawal exceeds the balance.
```

**Expected LLM behavior:**
- `class BankAccount` with `constructor(owner, balance)`
- Three instance methods
- Guard on `withdraw` that throws

**Pass criteria:** Class syntax, three methods, withdraw guard present  
**Fail criteria:** Function-based constructor, missing method, no guard on overdraft

---

### TC-AI-C-02 — Class with inheritance

**Priority:** Regression

**Prompt:**
```
Write a base class Animal with a constructor(name) and a method speak() that returns "...". Then write a subclass Dog that extends Animal and overrides speak() to return "${name} says: Woof!".
```

**Expected LLM behavior:**
- `class Animal` with `constructor` and `speak()`
- `class Dog extends Animal` with `super(name)` call
- Overridden `speak()` using `this.name`

**Pass criteria:** `extends`, `super()`, overridden method, `this.name` used  
**Fail criteria:** No `extends`, no `super`, copied constructor instead of inheriting

---

### TC-AI-C-03 — Class with private fields (ES2022)

**Priority:** Regression

**Prompt:**
```
Write a class Stack using private class fields (#items). Include methods push(item), pop(), peek(), and a getter size.
```

**Expected LLM behavior:**
- `#items = []` private field declaration
- `push`, `pop`, `peek` methods
- `get size()` getter

**Pass criteria:** `#items` private field used, getter present, all four members implemented  
**Fail criteria:** Uses `_items` convention instead of `#`, missing getter, missing `peek`

---

### TC-AI-C-04 — Singleton pattern

**Priority:** Regression

**Prompt:**
```
Write a JavaScript class Config that implements the Singleton pattern. It should have a method set(key, value) and get(key). Ensure only one instance is ever created.
```

**Expected LLM behavior:**
- Static `instance` property or variable
- Static `getInstance()` or constructor guard
- `set` and `get` backed by a plain object or Map

**Pass criteria:** Singleton guard present, `set`/`get` work, returns same instance on repeated calls  
**Fail criteria:** No instance control, multiple constructors allowed, missing methods

---

### TC-AI-C-05 — Observer / EventEmitter pattern

**Priority:** Regression

**Prompt:**
```
Write a class EventEmitter with methods on(event, listener), off(event, listener), and emit(event, ...args). Listeners registered for an event should all be called when emit is invoked.
```

**Expected LLM behavior:**
- Internal `Map` or plain object to store listeners per event
- `on` adds a listener, `off` removes it
- `emit` calls all listeners for the event with spread args

**Pass criteria:** Three methods, multiple listeners per event supported, `off` removes correctly  
**Fail criteria:** Only one listener per event, `off` not implemented, crashes on unknown event emit

---

### TC-AI-C-06 — Class with static factory method

**Priority:** Edge

**Prompt:**
```
Write a class Color with properties r, g, b. Add a static factory method Color.fromHex(hex) that parses a hex string like "#FF8800" and returns a Color instance.
```

**Expected LLM behavior:**
- `static fromHex(hex)` that parses and returns `new Color(r, g, b)`
- Hex parsing correct (handles `#` prefix)

**Pass criteria:** Static factory method, correct hex parsing, returns `Color` instance  
**Fail criteria:** Instance method instead of static, wrong parsing, no `new Color(...)` returned

---

### TC-AI-C-07 — Abstract-style base class (no real abstract in JS)

**Priority:** Edge

**Prompt:**
```
Write a base class Shape with a method area() that throws an Error "Not implemented". Then write subclasses Circle(radius) and Rectangle(width, height) that each override area() with the correct calculation.
```

**Expected LLM behavior:**
- `Shape.area()` throws `new Error("Not implemented")`
- `Circle` and `Rectangle` both `extends Shape` and override `area()`
- Correct formulas: `Math.PI * r²` and `w * h`

**Pass criteria:** Two subclasses, correct formulas, base throws  
**Fail criteria:** No base class, formulas wrong, no `extends`

---

### TC-AI-C-08 — Class with Symbol.iterator (iterable)

**Priority:** Edge

**Prompt:**
```
Write a class Range(start, end) that implements Symbol.iterator so it can be used in a for...of loop to iterate from start to end (inclusive).
```

**Expected LLM behavior:**
- `[Symbol.iterator]()` generator or object with `next()`
- Yields integers from `start` to `end`

**Pass criteria:** `Symbol.iterator` implemented, `for...of` compatible, inclusive range  
**Fail criteria:** No `Symbol.iterator`, array returned instead, exclusive end

---

## Category 3 — React Component Generation

### TC-AI-R-01 — Simple functional component

**Priority:** Smoke

**Prompt:**
```
Write a React functional component Greeting that accepts a name prop and renders <h1>Hello, {name}!</h1>.
```

**Expected LLM behavior:**
- `function Greeting({ name })` or arrow function
- Returns JSX: `<h1>Hello, {name}!</h1>`
- No class component

**Pass criteria:** Functional component, prop destructuring, correct JSX, no `React.Component`  
**Fail criteria:** Class component, missing prop, no JSX return

---

### TC-AI-R-02 — Component with PropTypes or TypeScript interface

**Priority:** Regression

**Prompt:**
```
Write a React functional component Button with props: label (string), onClick (function), and disabled (boolean, default false). The component should render a <button> element.
```

**Expected LLM behavior:**
- Functional component with three props
- Default value for `disabled`
- Passes `onClick` and `disabled` to `<button>`

**Pass criteria:** All three props used, `disabled` has default, `<button>` element rendered  
**Fail criteria:** Missing prop, no default for `disabled`, wrong HTML element

---

### TC-AI-R-03 — Component with `useState`

**Priority:** Smoke

**Prompt:**
```
Write a React component Counter that starts at 0 and renders the current count and two buttons: "Increment" and "Decrement".
```

**Expected LLM behavior:**
- `useState(0)` to track count
- Two button handlers updating state
- Current count displayed

**Pass criteria:** `useState` used, both buttons present, count displayed  
**Fail criteria:** Count as a variable (no state), missing button, state updated directly

---

### TC-AI-R-04 — Component with `useEffect` and cleanup

**Priority:** Regression

**Prompt:**
```
Write a React component Timer that displays a counter that increments every second using setInterval. Clean up the interval when the component unmounts.
```

**Expected LLM behavior:**
- `useEffect` with `setInterval`
- Returns a cleanup function that calls `clearInterval`
- Displays counter from state

**Pass criteria:** `useEffect` with cleanup return, `clearInterval` present, counter displayed  
**Fail criteria:** No cleanup, `setInterval` outside `useEffect`, no display of counter

---

### TC-AI-R-05 — Component with event handler and form input

**Priority:** Regression

**Prompt:**
```
Write a React controlled input component SearchBox that renders a text input. As the user types, display the current input value below the input field.
```

**Expected LLM behavior:**
- `useState` for input value
- `onChange` handler updating state
- Controlled `<input value={...} onChange={...} />`
- Displays value below

**Pass criteria:** Controlled input, state updates on change, value displayed below  
**Fail criteria:** Uncontrolled input (no `value` prop), value not shown, missing `onChange`

---

### TC-AI-R-06 — List rendering with `key` prop

**Priority:** Regression

**Prompt:**
```
Write a React component ItemList that accepts an items prop (array of objects with id and label). Render each item as an <li> inside a <ul>. Use the id as the key.
```

**Expected LLM behavior:**
- Maps over `items`
- Each `<li key={item.id}>{item.label}</li>`
- Wrapped in `<ul>`

**Pass criteria:** `key={item.id}` present, `item.label` rendered, `<ul>` wrapper  
**Fail criteria:** Missing `key`, index used as key, `<div>` instead of `<ul>`/`<li>`

---

### TC-AI-R-07 — Custom React hook

**Priority:** Regression

**Prompt:**
```
Write a custom React hook useLocalStorage(key, initialValue) that reads from and writes to localStorage. Return [value, setValue] like useState.
```

**Expected LLM behavior:**
- Function named `use...` (hook convention)
- `useState` initialized from `localStorage.getItem(key)`
- `setValue` updates both state and `localStorage`

**Pass criteria:** Hook naming convention, reads from `localStorage` on init, writes on update  
**Fail criteria:** Not a hook (no `use` prefix), ignores `localStorage`, `setValue` doesn't persist

---

### TC-AI-R-08 — Component with Tailwind CSS classes

**Priority:** Edge

**Prompt:**
```
Write a React component Card that renders a container with a white background, rounded corners, shadow, and padding. Display a title prop in a bold h2 and a description prop in a smaller paragraph. Use Tailwind CSS utility classes.
```

**Expected LLM behavior:**
- Tailwind classes like `bg-white`, `rounded`, `shadow`, `p-4`
- `<h2>` with `font-bold` or `font-semibold`
- `<p>` with smaller text class like `text-sm`

**Pass criteria:** Tailwind classes present, both props rendered, semantic HTML structure  
**Fail criteria:** Inline styles only, missing props, no Tailwind classes

---

### TC-AI-R-09 — Context-aware component using `useContext`

**Priority:** Edge

**Prompt:**
```
Write a React component ThemeToggle that reads the current theme ("light" or "dark") from a ThemeContext and renders a button to toggle between them. Assume ThemeContext provides { theme, setTheme }.
```

**Expected LLM behavior:**
- `useContext(ThemeContext)` call
- Button toggles between `"light"` and `"dark"`
- Button text reflects current theme

**Pass criteria:** `useContext` used, toggle logic correct, button text varies  
**Fail criteria:** Theme hardcoded, no `useContext`, toggle doesn't work

---

## Category 4 — LLM Response Behavior

### TC-AI-B-01 — Response contains markdown code fences

**Priority:** Smoke

**Prompt:**
```
Write a function hello() that returns the string "Hello, World!".
```

**Scenario:** LLM returns:
````
```javascript
function hello() {
  return "Hello, World!";
}
```
````

**Expected system behavior:**
- The frontend strips the markdown fences before inserting into the editor
- Editor contains only the raw code, no ` ``` ` characters

**Pass criteria:** Fences stripped, clean code in editor  
**Fail criteria:** Fences visible in editor, syntax error from inserted fences

---

### TC-AI-B-02 — Response contains explanation prose before the code

**Priority:** Regression

**Scenario:** LLM returns:
```
Here is the function you requested:

function hello() {
  return "Hello, World!";
}

This function returns the greeting string.
```

**Expected system behavior:**
- The system extracts the code block (between the first `function`/`const`/`class` and the last `}`)
- Or shows the full response and lets the user manually clean it up
- Must NOT silently insert the prose into the code editor (it would cause a syntax error)

**Pass criteria:** Either prose stripped and only code inserted, or user is notified  
**Fail criteria:** Full prose inserted into editor causing a syntax error

---

### TC-AI-B-03 — Empty response from LLM

**Priority:** Smoke

**Scenario:** LLM API returns `200 OK` with body `{ "code": "" }` or `{ "code": null }`.

**Expected system behavior:**
- No code is inserted into the editor
- A user-visible error message: "Generation failed — empty response" or equivalent
- The Generate button is re-enabled

**Pass criteria:** Error message shown, editor unchanged, button re-enabled  
**Fail criteria:** Empty string inserted, silent failure, button stuck in loading state

---

### TC-AI-B-04 — Response contains only whitespace

**Priority:** Regression

**Scenario:** LLM returns `{ "code": "   \n  \t  " }`.

**Expected system behavior:**
- Treated the same as an empty response (TC-AI-B-03)
- Trimmed content evaluated as empty
- Error message shown

**Pass criteria:** Whitespace-only treated as empty, error shown  
**Fail criteria:** Whitespace inserted, no error, editor shows blank content as "success"

---

### TC-AI-B-05 — Response contains syntactically invalid code

**Priority:** Regression

**Scenario:** LLM returns `{ "code": "function foo( { return 'unclosed';" }`.

**Expected system behavior:**
- Code is inserted into the editor as-is (the system does not block it)
- The user can edit the broken code
- Optionally: a warning indicator that the code has a syntax error

**Pass criteria:** Code inserted into editor for user review, no silent discard  
**Fail criteria:** Code silently discarded, app crashes, user sees no indication of the issue

---

### TC-AI-B-06 — Request timeout (> 30 seconds)

**Priority:** Smoke

**Scenario:** The backend or WASM LLM takes longer than 30 seconds to respond (per `docs/requirements.md` §3.2 LLM-NF-01).

**Expected system behavior:**
- The request is aborted client-side after the timeout threshold
- A user-visible error message: "Request timed out" or equivalent
- The Generate button is re-enabled
- No partial code is inserted

**Pass criteria:** Timeout detected, error message shown, button re-enabled, editor unchanged  
**Fail criteria:** Request hangs indefinitely, UI frozen, partial code inserted

---

### TC-AI-B-07 — Backend returns 500 Internal Server Error

**Priority:** Regression

**Scenario:** `POST /api/llm/generate` returns HTTP 500.

**Expected system behavior:**
- A user-visible error message indicating generation failed
- The Generate button re-enabled
- Editor unchanged

**Pass criteria:** Error message shown, button re-enabled, no code inserted  
**Fail criteria:** Silent failure, error thrown to console only, button stuck

---

### TC-AI-B-08 — Backend returns 429 Too Many Requests (rate limit)

**Priority:** Regression  
**Related API test:** TC-API-LLM (rate limiting)

**Scenario:** `POST /api/llm/generate` returns HTTP 429 with body `{ "error": "rate_limit_exceeded" }`.

**Expected system behavior:**
- A specific user-visible message: "Too many requests — please wait and try again" or equivalent
- Optionally: shows how long to wait (if `Retry-After` header is present)
- Button re-enabled after message shown

**Pass criteria:** Rate-limit-specific message shown, button re-enabled  
**Fail criteria:** Generic error shown (no distinction from 500), button stuck, no message

---

### TC-AI-B-09 — Prompt in a non-English language (Russian)

**Priority:** Regression

**Prompt:**
```
Напиши функцию, которая сортирует массив чисел по возрастанию.
```

**Expected system behavior:**
- The prompt is forwarded to the LLM as-is
- The LLM returns JavaScript code (not Russian text)
- Code is inserted into the editor

**Pass criteria:** Code in JS inserted, not Russian text, no client-side language filter  
**Fail criteria:** Prompt blocked by client, Russian text inserted, app crashes

---

### TC-AI-B-10 — Extremely short prompt

**Priority:** Edge

**Prompt:**
```
function
```

**Expected system behavior:**
- If minimum length validation exists: prompt blocked with a validation message
- If no minimum length: forwarded to LLM; result may be incomplete or a stub function
- No crash either way

**Pass criteria:** Either validation message shown OR LLM called and result handled gracefully  
**Fail criteria:** App crash, infinite loading, server error exposed raw to user

---

### TC-AI-B-11 — Generation cancelled mid-flight (streaming)

**Priority:** Edge  
**Applies when:** Streaming responses (SSE/WebSocket) are implemented per `docs/requirements.md` §3.2 LLM-NF-02.

**Scenario:**
1. User clicks "Generate"
2. Streaming begins — partial code appears in the editor
3. User clicks a "Cancel" button (or navigates away) before completion

**Expected system behavior:**
- The SSE/WebSocket stream is closed
- Partial code is either: (a) cleared from the editor, or (b) left for the user to review with a "generation cancelled" notice
- The Generate button is re-enabled

**Pass criteria:** Stream closed, button re-enabled, no duplicate requests on re-submit  
**Fail criteria:** Stream continues after cancel, button stuck, partial code inserted silently

---

## Appendix — Prompt coverage matrix

| TC ID | Category | Code structure | Error scenario | Smoke |
|---|---|---|---|---|
| TC-AI-F-01 | Function | Simple function | — | ✓ |
| TC-AI-F-02 | Function | Default params | — | |
| TC-AI-F-03 | Function | Async/await | — | |
| TC-AI-F-04 | Function | Error throwing | — | |
| TC-AI-F-05 | Function | Recursion + memo | — | |
| TC-AI-F-06 | Function | Closure / HOF | — | |
| TC-AI-F-07 | Function | Array transform | — | |
| TC-AI-F-08 | Function | Generator | — | |
| TC-AI-F-09 | Function | Pure / deep clone | — | |
| TC-AI-F-10 | Function | JSDoc | — | |
| TC-AI-F-11 | Function | Currying | — | |
| TC-AI-F-12 | Function | Composition | — | |
| TC-AI-C-01 | Class | Basic class | — | ✓ |
| TC-AI-C-02 | Class | Inheritance | — | |
| TC-AI-C-03 | Class | Private fields | — | |
| TC-AI-C-04 | Class | Singleton | — | |
| TC-AI-C-05 | Class | Observer/EventEmitter | — | |
| TC-AI-C-06 | Class | Static factory | — | |
| TC-AI-C-07 | Class | Abstract-style | — | |
| TC-AI-C-08 | Class | Iterable | — | |
| TC-AI-R-01 | React | Simple component | — | ✓ |
| TC-AI-R-02 | React | Props + defaults | — | |
| TC-AI-R-03 | React | useState | — | ✓ |
| TC-AI-R-04 | React | useEffect + cleanup | — | |
| TC-AI-R-05 | React | Controlled input | — | |
| TC-AI-R-06 | React | List + key prop | — | |
| TC-AI-R-07 | React | Custom hook | — | |
| TC-AI-R-08 | React | Tailwind CSS | — | |
| TC-AI-R-09 | React | useContext | — | |
| TC-AI-B-01 | Behavior | — | Markdown fences | ✓ |
| TC-AI-B-02 | Behavior | — | Prose in response | |
| TC-AI-B-03 | Behavior | — | Empty response | ✓ |
| TC-AI-B-04 | Behavior | — | Whitespace-only | |
| TC-AI-B-05 | Behavior | — | Invalid JS syntax | |
| TC-AI-B-06 | Behavior | — | Timeout (> 30s) | ✓ |
| TC-AI-B-07 | Behavior | — | 500 error | |
| TC-AI-B-08 | Behavior | — | 429 rate limit | |
| TC-AI-B-09 | Behavior | — | Non-English prompt | |
| TC-AI-B-10 | Behavior | — | Minimal prompt | |
| TC-AI-B-11 | Behavior | — | Cancel mid-stream | |

**Smoke subset (8 tests):** TC-AI-F-01, TC-AI-C-01, TC-AI-R-01, TC-AI-R-03, TC-AI-B-01, TC-AI-B-03, TC-AI-B-06 — these 7 cover the golden path for each code structure plus the three most critical LLM failure modes.

# Безопасное исполнение JS в браузере (sandbox для JS-Notebook)

> Файл — рекомендация, а не реализация. Текущее состояние:
> `ui/src/features/notebook/model/executeJS.ts` использует `new Function(...)`,
> что выполняет код в основном потоке, в том же origin, с полным доступом к
> `window`, `document`, `localStorage`, IndexedDB, cookies, сети и т.д.
> Это противоречит ТЗ (`docs/project.md`: «изолированная среда — iframe или
> Web Worker»).

---

## 1. Почему текущая реализация опасна

`new Function('console', 'return (async () => { ... })()')(sandboxConsole)`:

1. **Тот же realm**, что и приложение. Скрипт пользователя может:
   - читать/писать `localStorage`, IndexedDB (где живут ноутбуки и сессия),
   - делать `fetch('https://api.notebook.com/api/v1/...', {credentials:'include'})`
     с действующими cookies и подписанными CSRF-токенами,
   - менять DOM (XSS-эквивалент),
   - читать `document.cookie` (если не HttpOnly),
   - крутить бесконечный цикл и заморозить вкладку.
2. **Нет таймаута.** `while(true){}` повесит UI.
3. **Нет лимита памяти.** `Array(2**30)` уронит вкладку.
4. **Нет capture.** Перехватывается только `console.*`, но не `throw` внутри
   `setTimeout`, не `unhandledrejection`, не `document.write`.
5. **Нет отмены.** Если ячейка зависла, перезапустить можно только перезагрузкой.

В шаринг-сценарии (notebook от другого пользователя) это становится прямой
дыр­ой: чужой ноутбук = чужой код = полный доступ к вашему аккаунту.

---

## 2. Какие варианты изоляции бывают

| Подход | Изоляция | Сложность | Когда выбирать |
|---|---|---|---|
| `new Function` (сейчас) | Нулевая | 0 | Никогда для прод |
| **Web Worker** | Отдельный поток, нет DOM, нет `window` (но есть `self`, `fetch`, `IndexedDB`) | Низкая | Чисто вычислительные ячейки |
| **Sandboxed iframe** (`sandbox="allow-scripts"` без `allow-same-origin`) | Отдельный realm + null-origin → нет доступа к cookies/localStorage родителя, нет same-origin fetch | Средняя | Когда нужен DOM для отрисовки графиков, canvas, html-output |
| **Iframe + Worker внутри iframe** | Двойная: cross-origin iframe + отдельный поток | Средняя+ | Рекомендуемый продакшен-вариант |
| **QuickJS-WASM / SES (Hardened JavaScript)** | Изолированный JS-движок внутри JS | Высокая | Когда нужны жёсткие гарантии и детерминизм |
| **Server-side runtime (Deno/Node в контейнере)** | Полная изоляция через ОС/контейнер | Высокая, дорого | Когда нельзя доверять клиенту |

Для MVP оптимально: **sandboxed iframe + Web Worker внутри**.

---

## 3. Рекомендуемая архитектура (iframe + Worker)

```
┌─────────────────────────────────────────────┐
│ Главное приложение  (notebook.com)          │
│                                             │
│  Reatom store, IndexedDB, auth-сессия       │
│                                             │
│  ┌───────────────────────────────────────┐  │
│  │ <iframe sandbox="allow-scripts"        │  │
│  │   src="https://sandbox.notebook.com">  │  │  ← другой origin (или srcdoc)
│  │                                       │  │
│  │   ┌──────────────────────────────┐    │  │
│  │   │  Web Worker                  │    │  │  ← user JS живёт ЗДЕСЬ
│  │   │  - eval(code)                │    │  │
│  │   │  - console hook              │    │  │
│  │   │  - postMessage наружу        │    │  │
│  │   └──────────────────────────────┘    │  │
│  │                                       │  │
│  │   рендер html/canvas output из        │  │
│  │   разрешённого набора API             │  │
│  └───────────────────────────────────────┘  │
│            ▲ postMessage (структ. данные)   │
│            │                                │
└────────────┼────────────────────────────────┘
             │
   контракт: { type: 'run' | 'cancel',
               id, code }  →
              ← { type: 'log' | 'result' | 'error' | 'done',
                  id, payload }
```

Ключевые свойства:

- `sandbox="allow-scripts"` **без** `allow-same-origin` → iframe получает
  «null origin». Его `document.cookie`, `localStorage`, IndexedDB пустые и
  изолированы. `fetch` идёт без cookies родителя.
- Если iframe сервится с **другого домена** (`sandbox.notebook.com`),
  это вторая линия защиты (cookies настоящего домена недостижимы даже без
  атрибута sandbox).
- Worker внутри iframe даёт отдельный поток → таймаут `while(true)` тупо
  убивается `worker.terminate()`, главное приложение не виснет.
- Контракт между iframe и приложением — только `postMessage` со
  структурированными клонированными данными. Никаких функций/прокси.

---

## 4. Скелет реализации (без правок в проекте, для справки)

### 4.1. Worker-код (`sandbox/worker.ts`)

```ts
// Перехватываем console.* внутри worker
const wrappedConsole = {
  log:   (...a: unknown[]) => post({ type: 'log',   level: 'log',   args: a.map(String) }),
  warn:  (...a: unknown[]) => post({ type: 'log',   level: 'warn',  args: a.map(String) }),
  error: (...a: unknown[]) => post({ type: 'log',   level: 'error', args: a.map(String) }),
}

function post(msg: unknown) { self.postMessage(msg) }

self.onmessage = async (e) => {
  const { id, code } = e.data
  try {
    // важно: не отдаём пользовательскому коду глобалы;
    // создаём изолированный scope через async-функцию
    const fn = new Function('console',
      `"use strict"; return (async () => { ${code} \n })()`)
    const result = await fn(wrappedConsole)
    post({ type: 'result', id, payload: serialize(result) })
  } catch (err: any) {
    post({ type: 'error', id, message: String(err?.message ?? err), stack: err?.stack })
  } finally {
    post({ type: 'done', id })
  }
}

function serialize(v: unknown) {
  try { return JSON.parse(JSON.stringify(v)) } catch { return String(v) }
}
```

### 4.2. iframe-обёртка (`sandbox/index.html`)

```html
<!doctype html>
<meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; script-src 'self' blob:; worker-src 'self' blob:; connect-src 'none';">
<script type="module" src="/sandbox.js"></script>
```

`sandbox.js` создаёт worker, прокидывает сообщения от родителя в worker и обратно.

### 4.3. Хост (`shared/lib/runtime.ts`)

```ts
export interface RunOptions { timeoutMs?: number; signal?: AbortSignal }

export class NotebookRuntime {
  private iframe: HTMLIFrameElement
  private pending = new Map<string, (msg: any) => void>()

  constructor() {
    this.iframe = document.createElement('iframe')
    this.iframe.sandbox.value = 'allow-scripts'  // без allow-same-origin
    this.iframe.src = '/sandbox/index.html'      // лучше другой origin
    this.iframe.style.display = 'none'
    document.body.appendChild(this.iframe)
    window.addEventListener('message', this.onMessage)
  }

  run(code: string, opts: RunOptions = {}) {
    const id = crypto.randomUUID()
    return new Promise<{ logs: string[]; result?: unknown; error?: string }>((resolve) => {
      const logs: string[] = []
      let timer: any
      const handler = (msg: any) => {
        if (msg.id && msg.id !== id) return
        if (msg.type === 'log')    logs.push(msg.args.join(' '))
        if (msg.type === 'error')  { resolve({ logs, error: msg.message }); cleanup() }
        if (msg.type === 'result') resolve({ logs, result: msg.payload })
        if (msg.type === 'done')   cleanup()
      }
      const cleanup = () => { this.pending.delete(id); clearTimeout(timer) }
      this.pending.set(id, handler)

      timer = setTimeout(() => {
        this.terminate()
        resolve({ logs, error: `Timeout after ${opts.timeoutMs ?? 5000} ms` })
      }, opts.timeoutMs ?? 5000)

      opts.signal?.addEventListener('abort', () => {
        this.terminate()
        resolve({ logs, error: 'Aborted' })
      })

      this.iframe.contentWindow?.postMessage({ type: 'run', id, code }, '*')
    })
  }

  terminate() {
    this.iframe.remove()
    this.iframe = document.createElement('iframe') // пересоздаём
    /* ... */
  }

  private onMessage = (e: MessageEvent) => {
    if (e.source !== this.iframe.contentWindow) return
    const handler = this.pending.get(e.data?.id)
    handler?.(e.data)
  }
}
```

---

## 5. Что обязательно настроить (security checklist)

1. **Sandbox iframe** с `allow-scripts`, **без** `allow-same-origin`,
   `allow-popups`, `allow-top-navigation`.
2. **Другой origin** для sandbox (поддомен `sandbox.notebook.com`,
   или blob/data url). Это даёт cross-origin isolation.
3. **CSP** в iframe: `default-src 'none'; script-src 'self' blob:; connect-src 'none'`
   (если связь с сетью разрешать — только через белый список).
4. **postMessage origin check**: проверять `event.origin` строго.
5. **Timeout** на каждый run (5–10 сек по умолчанию, настраиваемо в UI).
6. **Cancel/Terminate**: `worker.terminate()` или пересоздание iframe.
7. **Лимит логов**: обрезать stdout, например, до 1 МБ или 10 000 строк, иначе
   `console.log` в цикле зальёт RAM.
8. **Перехват `unhandledrejection`** и `error` событий в worker.
9. **structuredClone** — все данные между iframe/worker и хостом
   сериализуются автоматически, функции/прокси не пройдут.
10. **Изолированные сессии**: каждая ячейка/ноутбук — свой worker или общий
    с явным reset; пользователь должен понимать модель.

### Опасные API, которые нельзя оставлять доступными

- `parent`, `top`, `opener` — отключаются null-origin sandbox автоматически.
- `Service Worker` registration — отключить через CSP.
- `SharedArrayBuffer` — только если включён cross-origin isolation
  (`COOP/COEP`); используйте осознанно.
- `WebUSB`, `WebBluetooth`, `WebSerial`, `getUserMedia` — заблокировать через
  Permissions Policy: `Permissions-Policy: usb=(), serial=(), bluetooth=()`.

---

## 6. Импорт пакетов в ноутбуке (опционально, на будущее)

ТЗ упоминает «NPM-пакеты через CDN». Это уже само по себе риск (RCE через
скомпрометированный пакет), поэтому:

- **Whitelist CDN**: только `esm.sh`, `cdn.jsdelivr.net` через CSP
  `script-src https://esm.sh https://cdn.jsdelivr.net`.
- **Subresource Integrity** там, где возможно.
- В UI показывать «вы импортируете внешний код, он будет выполнен в sandbox»,
  и логировать импорты в audit.
- Запрет на топ-уровневые `eval`, `Function` внутри импортов — на практике
  не запретить, но можно мониторить.

---

## 7. Что протестировать

| Тест | Что проверяем |
|---|---|
| `while(true){}` | таймаут срабатывает, UI не виснет |
| `fetch('https://api.notebook.com/api/v1/me')` | возвращает 401 (нет cookies) или CORS-ошибку |
| `document.cookie` | пусто |
| `localStorage.setItem('x','y')` | не задевает основной localStorage |
| `top.location = 'evil.com'` | блокируется sandbox |
| `console.log` в цикле 1e6 | логи обрезаются, RAM не течёт |
| `throw new Error('x')` | приходит `{type:'error', message:'x'}` |
| `Promise.reject('y')` | ловится `unhandledrejection` |
| `crypto.subtle` | работает (worker имеет crypto) |
| cancel-кнопка | `worker.terminate()` отдаёт `{error:'Aborted'}` |

---

## 8. Дорожная карта внедрения

1. **Шаг 1 (1–2 дня).** Заменить `new Function` на отдельный Web Worker
   без iframe. Это уже даёт изоляцию потока + таймаут + cancel. Покрывает
   80% риска.
2. **Шаг 2 (2–3 дня).** Перенести Worker внутрь sandboxed iframe того же
   origin (через `srcdoc` или `/sandbox/index.html`). CSP + null-origin.
3. **Шаг 3 (опц.).** Вынести iframe на отдельный поддомен
   `sandbox.notebook.com` со своим certificate + CSP. Это «правильно» с точки
   зрения cross-origin isolation, но требует доп. деплоймента в Nginx/proxy.
4. **Шаг 4 (опц.).** Добавить `QuickJS-WASM` как опциональный «strict» режим
   для шаринга ноутбуков от других пользователей.

---

## 9. Полезные ссылки

- MDN: [iframe sandbox](https://developer.mozilla.org/en-US/docs/Web/HTML/Element/iframe#sandbox)
- MDN: [Web Workers API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API)
- W3C: [Content Security Policy Level 3](https://www.w3.org/TR/CSP3/)
- Agoric SES / Hardened JavaScript: <https://github.com/endojs/endo/tree/master/packages/ses>
- QuickJS-WASM: <https://github.com/justjake/quickjs-emscripten>
- Cross-origin isolation (COOP/COEP): <https://web.dev/coop-coep/>

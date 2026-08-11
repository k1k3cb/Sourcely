# Sourcely · frontend

App con Next.js 16 (App Router) para el asistente RAG de Sourcely. Capa autenticada con dos rutas: `/chat` (preguntas con streaming sobre tus documentos) y `/documents` (subida por drag-and-drop con seguimiento de estado).

## Stack

- **Next.js 16** con App Router y Turbopack
- **React 19**
- **TypeScript 5**
- **Tailwind CSS v4** con tokens de tema
- **Sonner** para toasts
- **Vitest** + **Testing Library** para tests unitarios

## Setup

```bash
pnpm install
cp .env.local.example .env.local
# Apuntar NEXT_PUBLIC_API_URL al backend, por ejemplo http://localhost:8000
pnpm dev
```

App: `http://localhost:3000`.

## Scripts

```bash
pnpm dev          # servidor de desarrollo con Turbopack
pnpm build        # build de producción
pnpm start        # servir el build de producción
pnpm lint         # eslint
pnpm test         # vitest, corrida única
pnpm test:watch   # vitest, modo watch
```

## Layout

```
app/
  chat/           Ruta /chat (server: lookup de auth · client: ChatClient)
  documents/      Ruta /documents (server: lista precargada · client: dropzone)
  login/          /login (form contra /api/v1/auth/login)
  register/       /register (form contra /api/v1/auth/register)
  layout.tsx      Layout raíz, monta <Toaster /> y <ThemeToggle />
  globals.css     Tokens de diseño (variantes claro/oscuro)
components/
  AppHeader       Wordmark + nav, usado en rutas protegidas
  ChatClient      Chat con streaming y deep links en SourceCard
  DocumentsClient Dropzone + lista con toasts de confirmación de borrado
  SourceCard      Card de cita (jump a audio / deep link a PDF / resaltado)
  ThemeToggle     Switch claro/oscuro con persistencia en localStorage
  LogoutButton    Llama a /api/v1/auth/logout y redirige
lib/
  api.ts          Wrapper tipado de fetch, SSE streamQuery, getChunkText
  auth.ts         Forwarder de cookies server-side para fetches en SSR
proxy.ts          Guard de rutas (redirige a usuarios sin autenticar)
```

## SSR y cookies

El código de browser usa `lib/api.ts` con `credentials: "include"`. Los server components no pueden confiar en eso: leen la cookie `token` con `next/headers` y la pasan explícitamente al backend mediante `apiServerFetch` de `lib/auth.ts`.

## Tests

```bash
pnpm test
```

Seis tests cubren la superficie crítica:

1. `SourceCard` renderiza `view p. N` para PDFs y `jump to m:ss` para audio (estado idle).
2. `SourceCard` cambia al botón `stop` cuando el chunk es el audio activo.
3. El clic en stop invoca `onStopAudio` y elimina el control de jump del DOM.
4. `ChatClient` stremea tokens dentro del mensaje del asistente y termina con el evento `done`.
5. `ChatClient` muestra un evento `error` del stream como mensaje rojo y vuelve a habilitar el input.
6. `DocumentsClient` rechaza archivos que no sean PDF/audio y nunca llama al endpoint de upload.

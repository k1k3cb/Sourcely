# Sourcely · frontend

Aplicación con Next.js 16 (App Router) para el asistente RAG de Sourcely. Capa autenticada con dos rutas: `/chat` (preguntas con *streaming* sobre tus documentos) y `/documents` (subida por *drag & drop* con seguimiento de estado).

## Stack

- **Next.js 16** con App Router y Turbopack
- **React 19**
- **TypeScript 5**
- **Tailwind CSS v4** con tokens de tema
- **Sonner** para los avisos
- **Vitest** + **Testing Library** para los tests unitarios

## Setup

```bash
pnpm install
cp .env.local.example .env.local
# Apunta NEXT_PUBLIC_API_URL al backend, por ejemplo http://localhost:8000
pnpm dev
```

App: `http://localhost:3000`.

## Scripts

```bash
pnpm dev          # servidor de desarrollo con Turbopack
pnpm build        # build de producción
pnpm start        # servir el build de producción
pnpm lint         # eslint
pnpm test         # vitest, ejecución única
pnpm test:watch   # vitest, modo watch
```

## Layout

```
app/
  chat/           Ruta /chat (server: lookup de auth · client: ChatClient)
  documents/      Ruta /documents (server: lista precargada · client: dropzone)
  login/          /login (formulario contra /api/v1/auth/login)
  register/       /register (formulario contra /api/v1/auth/register)
  layout.tsx      Layout raíz, monta <Toaster /> y <ThemeToggle />
  globals.css     Tokens de diseño (variantes claro/oscuro)
components/
  AppHeader       Logotipo + navegación, usado en rutas protegidas
  ChatClient      Chat con streaming y enlaces directos en SourceCard
  DocumentsClient Zona de arrastre + lista con avisos de confirmación al borrar
  SourceCard      Tarjeta de cita (salto a audio / enlace directo a PDF / resaltado)
  ThemeToggle     Conmutador claro/oscuro con persistencia en localStorage
  LogoutButton    Llama a /api/v1/auth/logout y redirige
lib/
  api.ts          Wrapper tipado de fetch, SSE streamQuery, getChunkText
  auth.ts         Reenvío de cookies server-side para fetches en SSR
proxy.ts          Guardia de rutas (redirige a usuarios sin autenticar)
```

## SSR y cookies

El código de navegador usa `lib/api.ts` con `credentials: "include"`. Los *server components* no pueden fiarse de eso: leen la cookie `token` con `next/headers` y la pasan explícitamente al *backend* mediante `apiServerFetch` de `lib/auth.ts`.

## Tests

```bash
pnpm test
```

Seis tests cubren la superficie crítica:

1. `SourceCard` renderiza `view p. N` para PDF y `jump to m:ss` para audio (estado en reposo).
2. `SourceCard` cambia al botón `stop` cuando el *chunk* es el audio activo.
3. Al pulsar stop se invoca `onStopAudio` y el control de salto desaparece del DOM.
4. `ChatClient` envía los *tokens* en *streaming* al mensaje del asistente y termina con el evento `done`.
5. `ChatClient` muestra un evento `error` del *stream* como mensaje rojo y vuelve a habilitar la entrada de texto.
6. `DocumentsClient` rechaza ficheros que no sean PDF/audio y nunca llama al *endpoint* de subida.

# Auto-Scholar Frontend

Next.js 16 frontend for Auto-Scholar.

## Stack

- Next.js 16 + React 19
- TypeScript
- Zustand
- next-intl (en/zh)
- Tailwind CSS + Radix UI
- Vitest + Playwright

## Install

```bash
bun install
```

## Run

```bash
bun run dev
```

Default local URL: `http://localhost:3000`

## Environment

Create `.env.local` (optional):

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Scripts

```bash
bun run dev
bun run build
bun run start
bun run lint
bun test
bun run test:e2e
```

## Directory Highlights

- `src/app/` - App Router entry (`layout.tsx`, `page.tsx`)
- `src/components/console/` - Input, logs, chat, status
- `src/components/approval/` - Candidate paper approval UI
- `src/components/workspace/` - Draft rendering, citations, charts
- `src/store/research.ts` - Global state
- `src/lib/api/` - Backend API integration
- `src/i18n/messages/` - Language messages

## Quality Checks

```bash
bun x tsc --noEmit
bun run lint
bun test
```

## Related Docs

- [Root README](../README.md)
- [Development Guide](../docs/DEVELOPMENT.md)
- [API Reference](../docs/API.md)

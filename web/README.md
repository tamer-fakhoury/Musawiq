# Musawiq web

Next.js (App Router) + TypeScript + Tailwind CSS frontend for Musawiq.

## Requirements

- Node.js 20.9 or newer
- npm

## Install

```
npm install
```

## Run

```
npm run dev
```

The app is served at http://localhost:3000.

Other scripts:

```
npm run build
npm run start
npm run lint
npm test
```

## Pointing at the API

Copy `.env.example` to `.env.local` and set the backend base URL:

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

`NEXT_PUBLIC_API_BASE_URL` is read at build time, so restart the dev server (or
rebuild) after changing it. The `/health` page calls `${NEXT_PUBLIC_API_BASE_URL}/health`
and reports `ok`, `degraded`, or `unreachable`.

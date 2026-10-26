# Musawiq web

Next.js (App Router) + TypeScript + Tailwind CSS frontend for Musawiq.
The interface is Arabic and RTL.

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

Copy `.env.example` to `.env.local` and set the backend base URL and the demo
tenant identifiers:

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_DEMO_STORE_ID=<store uuid>
NEXT_PUBLIC_DEMO_USER_ID=<user uuid>
NEXT_PUBLIC_DEMO_USER_ROLE=owner
```

`NEXT_PUBLIC_*` values are read at build time, so restart the dev server (or
rebuild) after changing them. Every API call sends the demo tenant headers
`X-Store-Id`, `X-User-Id`, and `X-User-Role` (default `owner`).

## Screens

- `/campaigns` — create a campaign, list campaigns, and inspect ad sets and
  variations.
- `/campaigns/{id}/signals` — submit a seven-day metrics window per ad and view
  previously submitted windows.
- `/campaigns/{id}/analysis` — run an AI diagnosis, copy recommendations, and
  review previous analyses.
- `/health` — reports `ok`, `degraded`, or `unreachable` for the API.

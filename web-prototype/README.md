# OpenSmash web prototype

A deliberately small React site and Node server that lives beside the existing
`pipeline/website` work. It reads character portraits and metadata from
`pipeline/play/ui` and serves the existing browser engine from
`BattleShip/web-dist`; those outputs are not copied into this app.

## Run it

```bash
cd web-prototype
pnpm install
pnpm dev
```

Open <http://127.0.0.1:4174>. For a production-style run:

```bash
pnpm build
COOKIE_SECRET="replace-me" pnpm start
```

Use `PORT` to change the port. Set a stable, private `COOKIE_SECRET` in any real
deployment so validation cookies survive restarts and cannot be forged.

## Choose the featured characters

Edit `config/characters.json`. Each entry points at a pipeline character and a
vanilla fighter skeleton/moveset:

```json
{ "slug": "queen", "fighter": "kirby" }
```

Valid fighter names are `mario`, `fox`, `donkey`, `samus`, `luigi`, `link`,
`yoshi`, `captain`, `kirby`, `pikachu`, `purin`, and `ness`. The server skips an
entry when its portrait, metadata, or selected `.osb` bundle is missing.

## ROM gate

The browser computes the selected file's SHA-256 locally and sends only the
hash and byte count to `POST /api/validate-rom`. The server currently accepts
the exact `Super Smash Bros. (USA).z64` file in Downloads, then issues a signed,
HTTP-only, 30-day cookie. Add later accepted hashes to the `ROMS` map in
`server/index.js`. The engine routes return 401 without that cookie, and the
cookie itself is signed with HMAC-SHA-256.

The ROM file is never uploaded or stored. The current WASM package already
contains the project's extracted engine assets.

Use the `Dev: clear ROM` button in the header to expire the validation cookie
and exercise the first-run flow again.

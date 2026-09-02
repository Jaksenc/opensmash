FROM node:22-bookworm-slim AS build

RUN corepack enable && corepack prepare pnpm@11.5.0 --activate
WORKDIR /workspace/pipeline/web-prototype
COPY pipeline/web-prototype/package.json pipeline/web-prototype/pnpm-lock.yaml pipeline/web-prototype/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY pipeline/web-prototype/ ./
RUN pnpm build

FROM node:22-bookworm-slim
ENV NODE_ENV=production
RUN corepack enable && corepack prepare pnpm@11.5.0 --activate
WORKDIR /workspace/pipeline/web-prototype
COPY pipeline/web-prototype/package.json pipeline/web-prototype/pnpm-lock.yaml pipeline/web-prototype/pnpm-workspace.yaml ./
RUN pnpm install --prod --frozen-lockfile
COPY --from=build /workspace/pipeline/web-prototype/dist ./dist
COPY pipeline/web-prototype/server ./server
COPY pipeline/web-prototype/shared ./shared
COPY pipeline/web-prototype/config ./config
COPY pipeline/web-prototype/visual ./visual
# Generated immediately before Cloud Build from config/characters.json and
# committed pipeline/play outputs. No ignored web-dist character state enters
# the image.
COPY pipeline/web-prototype/.baked-characters/play /workspace/pipeline/play
COPY BattleShip/web-dist/index.html BattleShip/web-dist/BattleShip.js BattleShip/web-dist/BattleShip.wasm BattleShip/web-dist/manifest.json /workspace/BattleShip/web-dist/
COPY BattleShip/web-dist/files /workspace/BattleShip/web-dist/files
# In-browser asset extraction (BattleShip/docs/web_rom_extraction.md): Torch
# compiled to wasm + the recipe tree, and the worker/stager scripts. Without
# these the engine has no way to obtain BattleShip.o2r, which is deliberately
# absent from files/. A missing source path fails the build here, on purpose.
COPY BattleShip/web-dist/torch /workspace/BattleShip/web-dist/torch
COPY BattleShip/web-dist/rom-extract.js BattleShip/web-dist/torch-worker.js /workspace/BattleShip/web-dist/

USER node
EXPOSE 8080
CMD ["node", "server/index.js"]

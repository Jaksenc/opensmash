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
COPY pipeline/play/ui/joeyflynn /workspace/pipeline/play/ui/joeyflynn
COPY pipeline/play/ui/barackobama /workspace/pipeline/play/ui/barackobama
COPY pipeline/play/ui/queen /workspace/pipeline/play/ui/queen
COPY pipeline/play/ui/rohansahai /workspace/pipeline/play/ui/rohansahai
COPY BattleShip/web-dist/index.html BattleShip/web-dist/BattleShip.js BattleShip/web-dist/BattleShip.wasm BattleShip/web-dist/manifest.json /workspace/BattleShip/web-dist/
COPY BattleShip/web-dist/files /workspace/BattleShip/web-dist/files
COPY BattleShip/web-dist/bundles/joeyflynn* /workspace/BattleShip/web-dist/bundles/
COPY BattleShip/web-dist/bundles/barackobama* /workspace/BattleShip/web-dist/bundles/
COPY BattleShip/web-dist/bundles/queen* /workspace/BattleShip/web-dist/bundles/
COPY BattleShip/web-dist/bundles/rohansahai* /workspace/BattleShip/web-dist/bundles/

USER node
EXPOSE 8080
CMD ["node", "server/index.js"]

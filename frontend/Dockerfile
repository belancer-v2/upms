# syntax=docker/dockerfile:1
FROM node:22-alpine AS deps
WORKDIR /w
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /w
COPY --from=deps /w/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
# API_ORIGIN is baked into the /api rewrite at build time.
ARG API_ORIGIN=http://api:8000
ENV API_ORIGIN=$API_ORIGIN
RUN npm run build

FROM node:22-alpine
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S app && adduser -S app -G app -u 10001
WORKDIR /app
COPY --from=build --chown=app:app /w/.next/standalone ./
COPY --from=build --chown=app:app /w/.next/static ./.next/static
COPY --from=build --chown=app:app /w/public ./public
USER app
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD wget -qO- http://127.0.0.1:3000/ >/dev/null || exit 1
CMD ["node", "server.js"]

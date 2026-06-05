FROM node:22.13-alpine AS build

WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN npm install -g pnpm@11.5.1 \
    && pnpm config set minimum-release-age 0 \
    && pnpm install --frozen-lockfile

COPY . .
ENV NODE_OPTIONS=--max-old-space-size=2048
RUN pnpm build

FROM nginx:1.27-alpine

RUN apk add --no-cache curl

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 30000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:30000 >/dev/null || exit 1

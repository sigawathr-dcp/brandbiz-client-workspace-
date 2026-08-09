FROM node:20-alpine AS base
RUN corepack enable && corepack prepare pnpm@9 --activate

FROM base AS builder
WORKDIR /app
COPY package.json pnpm-lock.yaml* ./
RUN npm install
COPY . .
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ARG BACKEND_URL=http://backend-api:8000
ENV BACKEND_URL=$BACKEND_URL
RUN npm run build

FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
ENV PORT=3000
# Bind to all interfaces so Caddy (and docker-exec health checks) can reach the server.
# Without this Next.js standalone binds to process.env.HOSTNAME which Docker sets to
# the container ID — unreachable from outside the container → 502.
ENV HOSTNAME=0.0.0.0
CMD ["node", "server.js"]

FROM node:22-bookworm-slim AS ui
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN corepack enable && corepack prepare pnpm@10.20.0 --activate && pnpm install --frozen-lockfile
COPY index.html tsconfig.json vite.config.ts ./
COPY src ./src
COPY public ./public
RUN pnpm build
FROM python:3.12-slim
WORKDIR /app
COPY requirements-app.txt ./
RUN pip install --no-cache-dir -r requirements-app.txt
COPY backend ./backend
COPY data/cofid-normalized.json ./data/cofid-normalized.json
COPY --from=ui /app/dist ./dist
ENV PORT=10000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]

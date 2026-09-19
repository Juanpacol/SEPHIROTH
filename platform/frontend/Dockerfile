# Local dev only — mirrors `npm run dev -- --port 3100`. Not what Vercel
# builds from (it deploys straight from the repo via its own GitHub
# integration, no Dockerfile involved — see ARCHITECTURE.md's Deployment
# section). This exists solely so `docker compose up` can start Postgres,
# the API, and this dev server with one command instead of three terminals.
FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3100

CMD ["npm", "run", "dev", "--", "--port", "3100"]

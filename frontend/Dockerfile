FROM node:20-alpine AS dependencies

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci \
    --fetch-retries=5 \
    --fetch-retry-factor=2 \
    --fetch-retry-mintimeout=20000 \
    --fetch-retry-maxtimeout=120000 \
    --fetch-timeout=120000 \
    --maxsockets=1

FROM dependencies AS development

COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

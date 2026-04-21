FROM node:20 AS builder
WORKDIR /build
COPY package.json .
RUN npm install

FROM node:20-slim
WORKDIR /app
COPY --from=builder /build/node_modules ./node_modules
COPY . .

# SEED: F006 applies here too — final stage runs as root (no USER directive)
EXPOSE 3000
CMD ["node", "src/server.js"]

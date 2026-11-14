FROM node:20-alpine
WORKDIR /app
COPY dist/ ./dist/
COPY server/ ./server/
COPY package.json ./
CMD ["node", "server/index.js"]

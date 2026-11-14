FROM node:20-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY dist/ ./dist/
CMD ["node", "dist/server/index.js"]

FROM node:24-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
# Preload instrumentation.js so the Node SDK patches Express + pg before they load.
CMD ["node", "-r", "./dist/instrumentation.js", "./dist/server.js"]

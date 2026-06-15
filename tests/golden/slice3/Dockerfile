# syntax=docker/dockerfile:1
FROM node:20-slim

WORKDIR /app

# The node base image ships node and npm — no extra prep needed.

COPY . .
RUN npm install $(node -p "require('./package.json').dependencies.join(' ')")

EXPOSE 3000
CMD node src/index.js

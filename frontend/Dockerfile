# Frontend image, two stages:
#   1. "build": Node compiles the React app into plain static files
#   2. "serve": a tiny nginx serves those files (no Node in the final image)
#
# The API address is fixed at BUILD time, because the browser (not the server) calls the API:
#   docker build --build-arg VITE_API_URL=http://localhost:8000 -t eka-frontend frontend

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine AS serve
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1

# Build stage: compile the React app
FROM node:26-alpine AS build
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Serve stage: static files behind nginx
FROM nginx:alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80

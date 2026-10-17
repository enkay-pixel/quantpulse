# Build stage: compile the React app
FROM node:26-alpine AS build
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
# Relative: nginx forwards /api to the API container (see nginx.conf).
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Serve stage: static files behind nginx. A version tag rather than `alpine`, so a rebuild cannot
# quietly take a different image and Dependabot can propose the next one.
FROM nginx:1.31.6-alpine
# The image's start-up step that adds an IPv6 listener only edits the stock default.conf, which is
# replaced below. To decide that, it asks apk for nginx's manifest, and this image's apk can fetch
# a package index over the network to answer, with no timeout: a stalled download left nginx
# unstarted and the dashboard refusing every request. Serving static files must not need the
# network to start.
RUN rm -f /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80

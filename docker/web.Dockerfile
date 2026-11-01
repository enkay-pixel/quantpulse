# Tag and digest: the digest is what builds, so a rebuild of the same tag upstream cannot change
# the image underneath; the tag is for reading. Dependabot proposes both together.

# Build stage: compile the React app
FROM node:26-alpine@sha256:dbaa92e5758cbbcf85d65d5403fdb530fe3442cbe8c6dbfb7ef23365450d5070 AS build
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
# Relative: nginx forwards /api to the API container (see nginx.conf).
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Serve stage: static files behind nginx.
FROM nginx:1.31.8-alpine@sha256:785835ea65db4bba6f021acc0f3be91b0fef76a53fe41f8588c6698d2aed0606
# The image's start-up step that adds an IPv6 listener only edits the stock default.conf, which is
# replaced below. To decide that, it asks apk for nginx's manifest, and this image's apk can fetch
# a package index over the network to answer, with no timeout: a stalled download left nginx
# unstarted and the dashboard refusing every request. Serving static files must not need the
# network to start.
RUN rm -f /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80 3000

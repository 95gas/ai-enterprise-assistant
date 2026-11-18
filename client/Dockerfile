### BUILD IMAGE SETUP ###
# get image and setup environment
FROM node:22-slim as build
ARG DEPLOYMENT_ID
WORKDIR /client

# install packages
COPY ./package.json ./yarn.lock .
RUN yarn install

# copy code, configure client and build
COPY . .
COPY ./config/${DEPLOYMENT_ID}/ .
RUN rm -rf ./config
RUN yarn build

### RUN IMAGE SETUP ###
# get image and setup environment
FROM nginx:stable-alpine3.21
COPY --from=build /client/dist /usr/share/nginx/html
COPY --from=build /client/nginx.conf /etc/nginx/conf.d/default.conf

# expose port and run
EXPOSE 80
ENTRYPOINT ["nginx", "-g", "daemon off;"]
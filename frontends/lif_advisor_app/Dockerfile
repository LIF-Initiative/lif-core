# Stage 1: build the vite application
FROM node:20-alpine AS build

# Accept a build-time argument for the API URL
ARG LIF_ADVISOR_API_URL
ENV LIF_ADVISOR_API_URL=${LIF_ADVISOR_API_URL}

# Set working directory
WORKDIR /app

# Copy package files and install dependencies
COPY ./package.json ./package-lock.json ./
RUN apk update && apk upgrade && npm ci

# Copy the rest of the application
COPY . .

# Inject Vite environment variable and build
RUN echo "VITE_LIF_ADVISOR_API_URL=${LIF_ADVISOR_API_URL}" > .env && \
    npm run build

# Stage 2: serve the built app with nginx
FROM nginx:1.26-alpine AS serve

# Copy built files from the previous stage
COPY --from=build /app/dist /usr/share/nginx/html/

# Copy custom nginx config for SPA fallback routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose default Nginx port
EXPOSE 80

# Start Nginx in the foreground
CMD ["nginx", "-g", "daemon off;"]

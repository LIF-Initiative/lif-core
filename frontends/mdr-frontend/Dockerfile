# Stage 1: build the vite application
FROM node:20-alpine AS build

# Accept build-time arguments
ARG LIF_MDR_API_URL
ENV LIF_MDR_API_URL=${LIF_MDR_API_URL}
ARG GA_MEASUREMENT_ID
ENV GA_MEASUREMENT_ID=${GA_MEASUREMENT_ID}

# Set working directory
WORKDIR /app

# Copy package files and install dependencies
COPY ./package.json ./package-lock.json ./
RUN apk update && apk upgrade && npm ci

# Copy the rest of the application
COPY . .

# Inject Vite environment variables and build
RUN echo "VITE_API_URL=${LIF_MDR_API_URL}" > .env && \
    echo "VITE_GA_MEASUREMENT_ID=${GA_MEASUREMENT_ID}" >> .env && \
    npm run build

# Stage 2: serve the built app with nginx
FROM nginx:1.26-alpine AS serve

# Copy built files from the previous stage
COPY --from=build /app/dist /usr/share/nginx/html/

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose default Nginx port
EXPOSE 80

# Start Nginx in the foreground
CMD ["nginx", "-g", "daemon off;"]

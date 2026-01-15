# Build stage for frontend
FROM node:18-alpine as build-frontend
WORKDIR /app/client

# Accept build arguments for environment variables needed at build time
ARG VITE_CLERK_PUBLISHABLE_KEY
ENV VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY

COPY client/package*.json ./
RUN npm install
COPY client/ ./
RUN npm run build

# Runtime stage for backend
FROM python:3.11-slim
WORKDIR /app/server

# Install Python dependencies
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY server/ .

# Copy built frontend assets from build stage
COPY --from=build-frontend /app/client/dist ../client/dist

# Expose port
ENV PORT=8000
EXPOSE $PORT

# Run the app
CMD uvicorn app:app --host 0.0.0.0 --port $PORT

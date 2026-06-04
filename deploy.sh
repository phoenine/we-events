#!/bin/bash

# Local service deployment helper.
# Database schema setup is owned by supabase/README.md and migration SQL files.

set -e

COMPOSE=${COMPOSE:-docker-compose}
BACKEND_HEALTH_URL=${BACKEND_HEALTH_URL:-http://localhost:38001/api/docs}
FRONTEND_HEALTH_URL=${FRONTEND_HEALTH_URL:-http://localhost:30000}
RUN_INIT=${RUN_INIT:-true}

echo "Starting local deployment"

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running."
  exit 1
fi

if [ ! -f ".env" ]; then
  echo ".env not found. Docker Compose uses the root .env for orchestration values."
  exit 1
fi

echo "Building services"
$COMPOSE build

echo "Starting services"
$COMPOSE up -d

echo "Waiting for services"
sleep 20

echo "Checking backend"
if ! curl -f "$BACKEND_HEALTH_URL" >/dev/null 2>&1; then
  echo "Backend is not responding at $BACKEND_HEALTH_URL"
  $COMPOSE logs backend
  exit 1
fi

echo "Checking frontend"
if ! curl -f "$FRONTEND_HEALTH_URL" >/dev/null 2>&1; then
  echo "Frontend is not responding at $FRONTEND_HEALTH_URL"
  $COMPOSE logs frontend
  exit 1
fi

if [ "$RUN_INIT" = "true" ]; then
  echo "Running backend admin initialization"
  $COMPOSE exec -T backend python init_sys.py
else
  echo "Skipping backend admin initialization because RUN_INIT=$RUN_INIT"
fi

echo "Deployment completed"
echo "Frontend: $FRONTEND_HEALTH_URL"
echo "Backend API docs: $BACKEND_HEALTH_URL"

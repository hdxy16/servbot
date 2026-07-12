#!/bin/bash

PROJECT="GYM_BOT"

echo "Creating project structure: $PROJECT"

mkdir -p $PROJECT

cd $PROJECT || exit


# Основні файли
touch .env
touch config.py
touch main.py
touch requirements.txt
touch README.md


# Database
mkdir -p database/migrations
touch database/engine.py
touch database/models.py


# Bot structure
mkdir -p bot/handlers
mkdir -p bot/keyboards
mkdir -p bot/states
mkdir -p bot/middlewares
mkdir -p bot/filters


# Handlers
touch bot/handlers/admin.py
touch bot/handlers/trainer.py
touch bot/handlers/client_food.py
touch bot/handlers/client_gym.py


# Keyboards
touch bot/keyboards/reply.py
touch bot/keyboards/inline.py


# States
touch bot/states/fsm.py


# Middleware
touch bot/middlewares/auth.py


# Filters
touch bot/filters/role_filter.py


# Scheduler
mkdir -p scheduler
touch scheduler/cron_jobs.py


# Init files для Python пакетів
touch database/__init__.py
touch bot/__init__.py
touch bot/handlers/__init__.py
touch bot/keyboards/__init__.py
touch bot/states/__init__.py
touch bot/middlewares/__init__.py
touch bot/filters/__init__.py
touch scheduler/__init__.py


echo "Structure created successfully!"

tree $PROJECT

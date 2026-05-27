#!/bin/bash
# Setup user-data directory structure for daily dashboard
# Design doc: ac-daily-dashboard-design-V1.0-ACTIVE.md | TODO: DB1

USER_DATA="/home/ubuntu/.openclaw/user-data"

echo "📁 Creating user-data directory structure..."

mkdir -p "$USER_DATA/news"
mkdir -p "$USER_DATA/profiles"
mkdir -p "$USER_DATA/logs"

# Create initial empty files for each data store
touch "$USER_DATA/card-registry.json"
touch "$USER_DATA/dashboard-config.json"
touch "$USER_DATA/todos.json"
touch "$USER_DATA/recipe.json"
touch "$USER_DATA/wishes.json"
touch "$USER_DATA/news/sources.json"
touch "$USER_DATA/profiles/admin.json"
touch "$USER_DATA/profiles/partner.json"
touch "$USER_DATA/logs/commands.jsonl"

chmod -R 755 "$USER_DATA"

echo "✅ user-data directory structure created at $USER_DATA"
ls -la "$USER_DATA"

#!/usr/bin/env sh

./telegram-bot.py &
uvicorn server:app --port 5001 --reload &
uvicorn notify-bot:app --port 5002 --reload

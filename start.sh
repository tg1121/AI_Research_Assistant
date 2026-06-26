#!/bin/sh
set -e
exec uvicorn backend.main:app --host 0.0.0.0 --port 7860

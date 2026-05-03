#!/bin/bash
cd /home/agentuser/hyperframes_projects
/home/agentuser/.hermes/hermes-agent/venv/bin/gunicorn -w 4 -b 0.0.0.0:8766 --timeout 600 --worker-class sync --access-logfile - hyperframes_app:app

#!/bin/bash
set -e

python scheduler.py &
uvicorn api_server:app --host 0.0.0.0 --port 8000 &
streamlit run dashboard.py --server.port=8501 --server.address=0.0.0.0
wait
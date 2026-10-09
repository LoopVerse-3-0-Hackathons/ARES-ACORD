FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt /tmp/api.txt
COPY frontend/requirements.txt /tmp/ui.txt
RUN pip install --no-cache-dir -r /tmp/api.txt -r /tmp/ui.txt
COPY backend ./backend
COPY frontend ./frontend
EXPOSE 8000 8501

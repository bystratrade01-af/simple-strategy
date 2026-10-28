FROM python:3.12-slim
WORKDIR /app
COPY monitor_worker.py ./
COPY ict_team_setup ./ict_team_setup
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
CMD ["python", "-B", "monitor_worker.py"]

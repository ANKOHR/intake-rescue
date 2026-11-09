FROM python:3.12.9-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt && useradd --create-home app && mkdir /srv/data && chown app:app /srv/data
COPY app ./app
USER app
EXPOSE 8765
CMD ["uvicorn","app.main:create_app","--factory","--host","0.0.0.0","--port","8765","--no-access-log"]

FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt
EXPOSE 8000 8501
CMD ["bash", "entrypoint.sh"]

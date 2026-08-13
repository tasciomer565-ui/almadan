# Almadan Scraper API — Fly.io için.
# Build context REPO KÖKÜ olmalı (app/ paketine erişebilmek için) --
# fly.toml'daki [build] dockerfile yolu bunu buna göre ayarlıyor.
FROM python:3.13-slim

WORKDIR /srv

# Tam requirements.txt kullanılıyor (scraper_api/requirements.txt değil) --
# app/search_orchestrator.py ve app/comparator.py çalışma zamanında
# app/ içindeki diğer modülleri de (fonksiyon içi import'lar dahil)
# çekebiliyor, minimal liste eksik kalabilirdi.
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scraper_api ./scraper_api

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

CMD ["uvicorn", "scraper_api.main:app", "--host", "0.0.0.0", "--port", "8080"]

"""
Sprint 2 — Veri İstihbaratı: Market Scraper Paketi

Desteklenen marketler: Migros, CarrefourSA, A101
Her scraper BaseScraper'dan miras alır.
"""
from app.scrapers.migros import MigrosScraper
from app.scrapers.carrefoursa import CarrefourSAScraper
from app.scrapers.a101 import A101Scraper

__all__ = ["MigrosScraper", "CarrefourSAScraper", "A101Scraper"]

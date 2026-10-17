"""Finder agent: collect businesses from open data (OpenStreetMap) or a CSV you provide."""
from __future__ import annotations

import csv
from pathlib import Path

import httpx

from .config import settings

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

NICHE_TAGS: dict[str, list[str]] = {
    "dentist": ['"amenity"="dentist"'],
    "clinic": ['"amenity"="clinic"', '"amenity"="doctors"'],
    "gym": ['"leisure"="fitness_centre"'],
    "real_estate": ['"office"="estate_agent"'],
    "restaurant": ['"amenity"="restaurant"'],
    "salon": ['"shop"="hairdresser"', '"shop"="beauty"'],
    "lawyer": ['"office"="lawyer"'],
    "accountant": ['"office"="accountant"'],
    "school": ['"amenity"="school"'],
}


def from_csv(path: str | Path) -> list[dict]:
    """CSV needs columns: name, website (city and niche are optional)."""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            if row.get("name") and row.get("website"):
                rows.append(row)
    return rows


def build_query(niche: str, city: str, limit: int) -> str:
    if niche in NICHE_TAGS:
        tags = NICHE_TAGS[niche]
    elif "=" in niche:  # raw OSM tag, e.g. shop=bakery
        key, value = niche.split("=", 1)
        tags = [f'"{key.strip()}"="{value.strip()}"']
    else:
        raise ValueError(
            f"Unknown niche '{niche}'. Use one of {sorted(NICHE_TAGS)} or a raw OSM tag like shop=bakery."
        )
    city = city.replace('"', "")
    parts = "".join(f'nwr[{t}]["website"](area.a);' for t in tags)
    return (
        "[out:json][timeout:40];"
        f'area["name"="{city}"]["boundary"="administrative"]->.a;'
        f"({parts});out tags {int(limit) * 3};"
    )


def from_osm(niche: str, city: str, limit: int = 20) -> list[dict]:
    query = build_query(niche, city, limit)
    r = httpx.post(
        OVERPASS_URL, data={"data": query}, timeout=60,
        headers={"User-Agent": settings.user_agent},
    )
    r.raise_for_status()
    out: list[dict] = []
    for el in r.json().get("elements", []):
        tags = el.get("tags", {})
        site = tags.get("website") or tags.get("contact:website")
        name = tags.get("name")
        if site and name:
            out.append({"name": name, "website": site, "city": city, "niche": niche})
        if len(out) >= limit:
            break
    return out

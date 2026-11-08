#!/usr/bin/env python3
"""
Generador diario de 'Noticias debajo de la tierra'.
Extrae RSS con imágenes de prensa española, internacional y deportiva.
Analiza sesgos, puntos ciegos y redacta con enfoque progresista riguroso (sin clickbait).
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

import feedparser
import requests
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# Configuración ampliada de fuentes RSS (Nacional, Internacional y Deportes)
FEEDS = {
    # --- ESPAÑA: IZQUIERDA / PROGRESISTA ---
    "El País": {
        "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
        "bias": "izquierda",
        "category": "nacional",
    },
    "elDiario.es": {
        "url": "https://www.eldiario.es/rss/",
        "bias": "izquierda",
        "category": "nacional",
    },
    "El Salto": {
        "url": "https://www.elsaltodiario.com/general/feed",
        "bias": "izquierda",
        "category": "nacional",
    },
    "Público": {
        "url": "https://www.publico.es/rss/",
        "bias": "izquierda",
        "category": "nacional",
    },
    "infoLibre": {
        "url": "https://www.infolibre.es/rss/",
        "bias": "izquierda",
        "category": "nacional",
    },
    # --- ESPAÑA: CENTRO / AGENCIAS / SÍNTESIS ---
    "20minutos": {
        "url": "https://www.20minutos.es/rss/",
        "bias": "centro",
        "category": "nacional",
    },
    "La Vanguardia": {
        "url": "https://www.lavanguardia.com/rss/home.xml",
        "bias": "centro",
        "category": "nacional",
    },
    "Kloshletter": {
        "url": "https://kloshletter.substack.com/feed",
        "bias": "centro",
        "category": "nacional",
    },
    # --- ESPAÑA: DERECHA / CONSERVADOR ---
    "El Mundo": {
        "url": "https://e00-elmundo.uecdn.es/elmundo/rss/portada.xml",
        "bias": "derecha",
        "category": "nacional",
    },
    "ABC": {
        "url": "https://www.abc.es/rss/2.0/portada/",
        "bias": "derecha",
        "category": "nacional",
    },
    "La Razón": {
        "url": "https://www.larazon.es/rss/portada.xml",
        "bias": "derecha",
        "category": "nacional",
    },
    # --- INTERNACIONAL ---
    "The Guardian": {
        "url": "https://www.theguardian.com/world/rss",
        "bias": "izquierda",
        "category": "internacional",
    },
    "The New York Times": {
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "bias": "centro",
        "category": "internacional",
    },
    "BBC World": {
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "bias": "centro",
        "category": "internacional",
    },
    "Le Monde": {
        "url": "https://www.lemonde.fr/rss/une.xml",
        "bias": "izquierda",
        "category": "internacional",
    },
    "The New Yorker": {
        "url": "https://www.newyorker.com/feed/news",
        "bias": "izquierda",
        "category": "internacional",
    },
    # --- DEPORTES ("Habla con un hetero") ---
    "Marca": {
        "url": "https://e00-marca.uecdn.es/rss/portada.xml",
        "bias": "deportes",
        "category": "deportes",
    },
    "El País Deportes": {
        "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/deportes/portada",
        "bias": "deportes",
        "category": "deportes",
    },
}

MAX_ITEMS_PER_FEED = 8
OUTPUT_PATH = Path(__file__).parent / "public" / "data.json"


# --- Esquemas Pydantic para Structured Outputs de Gemini ---

class CoverageDistribution(BaseModel):
    left: int = Field(description="Porcentaje de cobertura de medios de izquierda (0-100)")
    center: int = Field(description="Porcentaje de cobertura de medios de centro (0-100)")
    right: int = Field(description="Porcentaje de cobertura de medios de derecha (0-100)")


class BlindspotInfo(BaseModel):
    has_blindspot: bool = Field(description="True si algún bloque ideológico ignora o apenas cubre el tema")
    ignored_by: Literal["izquierda", "derecha", "centro", "ninguno"] = Field(
        description="Bloque ideológico para el que esta noticia es un punto ciego"
    )
    explanation: str = Field(
        description="Breve explicación de por qué es un punto ciego o qué enfoque omite ese bloque (vacío si no hay blindspot)"
    )


class MediaPerspective(BaseModel):
    source_name: str = Field(description="Nombre del medio (ej. El País, El Mundo, ABC, The Guardian, NYT...)")
    bias: Literal["izquierda", "centro", "derecha"] = Field(description="Ubicación ideológica del medio")
    headline: str = Field(description="Titular original del medio (traducido si está en otro idioma, o con el original)")
    angle: str = Field(description="Cómo enfoca o enmarca la noticia este medio (1-2 frases concisas)")
    url: str = Field(description="URL directa al artículo original")


class TopicItem(BaseModel):
    id: int = Field(description="Identificador numérico del tema (1 a 5)")
    category: str = Field(description="Categoría temática (ej. Vivienda, Trabajo, Sanidad, Geopolítica, Clima, Derechos)")
    editorial_title: str = Field(
        description="Titular propio con enfoque progresista riguroso, sobrio, directo y CERO clickbait"
    )
    image_url: str = Field(
        description="URL de la foto más representativa extraída de los artículos de entrada para esta noticia (vacío '' si ninguno trae imagen)"
    )
    image_caption: str = Field(description="Pie de foto breve o atribución del medio de la imagen")
    executive_summary: str = Field(
        description="Resumen ejecutivo de 1 párrafo con voz editorial de izquierdas pero analítica, rigurosa, explicando el trasfondo material/social y sin propaganda ni sensacionalismo"
    )
    coverage: CoverageDistribution
    blindspot: BlindspotInfo
    perspectives: List[MediaPerspective] = Field(
        description="Lista de medios que cubren este tema con su enfoque y enlace original"
    )


class SportsPill(BaseModel):
    competition: str = Field(description="Competición (ej. LaLiga, Champions, Selección, Tenis / F1)")
    headline: str = Field(description="Resultado o titular directo (ej. 'Barça 3 - 1 Atlético: remontada con doblete de Pedri')")
    talking_point: str = Field(
        description="1 o 2 frases con lo justo que necesitas saber: quién marcó los goles, la polémica arbitral o el dato clave para sobrevivir a una charla de ascensor o cafetería"
    )
    url: str = Field(description="URL a la crónica deportiva original")


class SportsSection(BaseModel):
    intro_joke: str = Field(
        description="Subtítulo irónico de 1 frase para abrir la sección 'Habla con un hetero' (kit de supervivencia futbolera del día)"
    )
    matches_and_news: List[SportsPill] = Field(
        description="Entre 3 y 4 píldoras ultrabreves con resultados de fútbol español, goleadores y el tema deportivo del día"
    )


class DailyEdition(BaseModel):
    edition_title: str = Field(description="Subtítulo editorial sobrio que resuma la jornada")
    daily_briefing: str = Field(
        description="Saludo matinal de 2-3 frases con tono cercano, inteligente y progresista (estilo boletín de autor) resumiendo por dónde va el día en España y el mundo"
    )
    spain_topics: List[TopicItem] = Field(description="Las 5 grandes noticias del día en España")
    international_topics: List[TopicItem] = Field(
        description="Las 5 grandes noticias internacionales del día (usando The Guardian, NYT, BBC, Le Monde, The New Yorker y prensa nacional)"
    )
    habla_con_un_hetero: SportsSection = Field(
        description="Sección 'Habla con un hetero': resumen brevísimo del fútbol y deporte más relevante en España"
    )


def clean_html(raw_html: str) -> str:
    """Elimina etiquetas HTML básicas y limpia espacios."""
    if not raw_html:
        return ""
    clean = re.sub(r"<[^>]+>", " ", raw_html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:420] + ("..." if len(clean) > 420 else "")


def extract_image_from_entry(entry: dict) -> str:
    """Extrae la URL de la imagen desde media_content, media_thumbnail, enclosures o el HTML del RSS."""
    # 1. media_content
    media_content = entry.get("media_content", [])
    if isinstance(media_content, list):
        for m in media_content:
            url = m.get("url", "")
            if url and (url.startswith("http://") or url.startswith("https://")):
                return url

    # 2. media_thumbnail
    media_thumb = entry.get("media_thumbnail", [])
    if isinstance(media_thumb, list):
        for m in media_thumb:
            url = m.get("url", "")
            if url and (url.startswith("http://") or url.startswith("https://")):
                return url

    # 3. links / enclosures de tipo imagen
    for link in entry.get("links", []) + entry.get("enclosures", []):
        ltype = link.get("type", "")
        href = link.get("href", "") or link.get("url", "")
        if href and ("image" in ltype or re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", href, re.I)):
            return href

    # 4. Buscar <img src="..."> dentro de summary o content
    html_blobs = [entry.get("summary", ""), entry.get("description", "")]
    for c in entry.get("content", []):
        if isinstance(c, dict):
            html_blobs.append(c.get("value", ""))

    for blob in html_blobs:
        if blob:
            match = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', blob, re.I)
            if match:
                img_url = match.group(1)
                if "pixel" not in img_url.lower() and "tracker" not in img_url.lower():
                    return img_url

    return ""


def fetch_kloshletter_fallback(headers: dict) -> list:
    """Fallback para Kloshletter usando rss2json y la API JSON de Substack."""
    items = []
    rss2json_url = "https://api.rss2json.com/v1/api.json?rss_url=https://kloshletter.substack.com/feed"
    try:
        resp = requests.get(rss2json_url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "ok" and data.get("items"):
            for entry in data["items"][:MAX_ITEMS_PER_FEED]:
                title = (entry.get("title") or "").strip()
                summary = clean_html(entry.get("description") or entry.get("content") or "")
                link = (entry.get("link") or "").strip()
                img = (entry.get("thumbnail") or "").strip()
                if title and link:
                    items.append({"title": title, "description": summary, "url": link, "image_url": img})
            if items:
                return items
    except Exception as e:
        print(f"   ⚠️ Fallback rss2json falló: {e}")

    substack_api_url = "https://kloshletter.substack.com/api/v1/posts?limit=5"
    try:
        resp = requests.get(substack_api_url, headers=headers, timeout=15)
        resp.raise_for_status()
        posts = resp.json()
        if isinstance(posts, list):
            for post in posts[:MAX_ITEMS_PER_FEED]:
                title = (post.get("title") or "").strip()
                summary = clean_html(post.get("subtitle") or post.get("description") or post.get("truncated_body_text") or "")
                link = (post.get("canonical_url") or "").strip()
                img = (post.get("cover_image") or "").strip()
                if not link and post.get("slug"):
                    link = f"https://kloshletter.substack.com/p/{post['slug']}"
                if title and link:
                    items.append({"title": title, "description": summary, "url": link, "image_url": img})
    except Exception as e:
        print(f"   ⚠️ Fallback API Substack falló: {e}")

    return items


def fetch_rss_items() -> dict:
    """Descarga y parsea titulares, descripciones e imágenes de cada medio."""
    collected = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
    }

    for source_name, meta in FEEDS.items():
        url = meta["url"]
        print(f"📡 Leyendo RSS de {source_name} ({url})...")
        feed = None
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception as e:
            print(f"⚠️ Aviso en {source_name} ({e}), reintentando...")
            feed = feedparser.parse(url, request_headers=headers)

        items = []
        if feed and getattr(feed, "entries", None):
            for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
                title = entry.get("title", "").strip()
                summary = clean_html(entry.get("summary", entry.get("description", "")))
                link = entry.get("link", "").strip()
                image_url = extract_image_from_entry(entry)
                if title and link:
                    items.append({
                        "title": title,
                        "description": summary,
                        "url": link,
                        "image_url": image_url,
                    })

        if not items and source_name == "Kloshletter":
            items = fetch_kloshletter_fallback(headers)

        collected[source_name] = {
            "bias": meta["bias"],
            "category": meta["category"],
            "items": items,
        }
        imgs_count = sum(1 for it in items if it.get("image_url"))
        print(f"   ✓ {len(items)} artículos ({imgs_count} con foto) de {source_name}.")

    return collected


def analyze_with_gemini(rss_data: dict) -> dict:
    """Envía los titulares a Gemini 3.8 Flash y devuelve el JSON estructurado."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: La variable de entorno GEMINI_API_KEY no está definida.", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    prompt = f"""
Eres el director editorial de **"Noticias debajo de la tierra"**, un diario digital matinal en España.

### LÍNEA EDITORIAL Y TONO:
- **Enfoque progresista / de izquierdas, pero riguroso, adulto y CERO clickbait**: No buscas una falsa equidistancia aséptica, sino un periodismo con sensibilidad social (atención a vivienda, servicios públicos, condiciones materiales, derechos laborales, emergencia climática y derechos humanos), pero **rechazas la propaganda, el lenguaje panfletario y los titulares sensacionalistas o clickbaiters**.
- Los titulares (`editorial_title`) deben ser informativos, sobrios, con sujeto y predicado claros, explicando qué pasa realmente.
- Al mismo tiempo, muestras con total honestidad el **radar de cobertura mediática** (cómo enfoca cada tema la izquierda, el centro y la derecha) para romper cámaras de eco.

### FUENTES DISPONIBLES:
1. **España**:
   - *Izquierda*: El País, elDiario.es, El Salto, Público, infoLibre.
   - *Centro / Síntesis*: 20minutos, La Vanguardia, Kloshletter (útil como termómetro de resumen matinal).
   - *Derecha*: El Mundo, ABC, La Razón.
2. **Internacional**:
   - The Guardian, The New York Times, BBC World, Le Monde, The New Yorker (más la cobertura internacional de los diarios españoles).
3. **Deportes**:
   - Marca, El País Deportes.

### ESTRUCTURA QUE DEBES GENERAR:
1. **`spain_topics` (Las 5 grandes noticias del día en España)**:
   - Agrupa las noticias de los diarios españoles en los 5 grandes temas de la jornada.
   - Para cada tema, elige la mejor `image_url` real de entre los artículos de entrada que cubren ese tema (no inventes URLs de imágenes; copia exactamente una `image_url` válida del JSON de entrada).
   - Calcula `coverage` (`left`, `center`, `right` sumando 100) y detecta `blindspot` (si la derecha o la izquierda ignoran un tema importante).
   - Incluye entre 3 y 5 `perspectives` comparando titulares reales de izquierda, centro y derecha con sus enlaces originales.

2. **`international_topics` (Las 5 grandes noticias internacionales del día)**:
   - Agrupa las 5 historias globales más importantes cruzando *The Guardian*, *The New York Times*, *BBC World*, *Le Monde*, *The New Yorker* y las secciones internacionales españolas.
   - Todo redactado en español. En `perspectives`, incluye los medios internacionales que la cubren (puedes traducir o explicar su enfoque en español conservando su `url` original).
   - Asigna también `image_url` real extraída de las entradas, barra de `coverage` y `blindspot`.

3. **`habla_con_un_hetero` (Sección final de supervivencia deportiva/futbolera)**:
   - Una sección breve, ágil y con un guiño irónico pensada para enterarse en 30 segundos del deporte más relevante en España (especialmente fútbol: resultados de LaLiga/Champions/Selección, **quién marcó los goles**, o la noticia deportiva del día).
   - Genera entre 3 y 4 píldoras (`matches_and_news`) directas al grano con resultado, goleadores y enlace original.

Datos RSS de entrada (JSON):
{json.dumps(rss_data, ensure_ascii=False, indent=2)}
"""

    models_to_try = ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash"]
    last_err = None
    for model_name in models_to_try:
        try:
            print(f"🧠 Analizando noticias con Gemini ({model_name})...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DailyEdition,
                    temperature=0.25,
                ),
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"⚠️ Modelo {model_name} no disponible ({e}), probando siguiente...")
            last_err = e

    raise RuntimeError(f"No se pudo generar contenido con ningún modelo de Gemini: {last_err}")


def main():
    rss_data = fetch_rss_items()
    edition_data = analyze_with_gemini(rss_data)

    now = datetime.now(timezone.utc).astimezone()
    final_payload = {
        "generated_at": now.isoformat(),
        "date_formatted": now.strftime("%d de %B de %Y"),
        "sources_count": len(FEEDS),
        **edition_data,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, ensure_ascii=False, indent=2)

    print(f"✅ Archivo generado con éxito en: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

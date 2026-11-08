#!/usr/bin/env python3
"""
Generador diario de noticias (estilo Ground News + Kloshletter).
Extrae RSS de medios españoles e internacionales, analiza sesgos y puntos ciegos
con Gemini (google-genai) y guarda el resultado en public/data.json.
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

# Configuración de fuentes RSS y su clasificación orientativa para el análisis
FEEDS = {
    "Kloshletter": {
        "url": "https://kloshletter.substack.com/feed",
        "bias": "centro",
        "category": "nacional",
    },
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
    "El Mundo": {
        "url": "https://e00-elmundo.uecdn.es/elmundo/rss/portada.xml",
        "bias": "derecha",
        "category": "nacional",
    },
    "El Salto": {
        "url": "https://www.elsaltodiario.com/general/feed",
        "bias": "izquierda",
        "category": "nacional",
    },
    "The New Yorker": {
        "url": "https://www.newyorker.com/feed/news",
        "bias": "internacional",
        "category": "internacional",
    },
}

MAX_ITEMS_PER_FEED = 10
OUTPUT_PATH = Path(__file__).parent / "public" / "data.json"


# --- Esquemas Pydantic para Structured Outputs de Gemini ---

class CoverageDistribution(BaseModel):
    left: int = Field(description="Porcentaje de cobertura de medios de izquierda (0-100)")
    center: int = Field(description="Porcentaje de cobertura de medios de centro/resumen (0-100)")
    right: int = Field(description="Porcentaje de cobertura de medios de derecha (0-100)")


class BlindspotInfo(BaseModel):
    has_blindspot: bool = Field(description="True si algún espectro ideológico ignora o apenas cubre el tema")
    ignored_by: Literal["izquierda", "derecha", "centro", "ninguno"] = Field(
        description="Bloque ideológico para el que esta noticia es un punto ciego"
    )
    explanation: str = Field(
        description="Breve explicación de por qué es un punto ciego o qué enfoque falta (vacío si no hay blindspot)"
    )


class MediaPerspective(BaseModel):
    source_name: str = Field(description="Nombre del medio (ej. El País, El Mundo, elDiario.es, El Salto, Kloshletter)")
    bias: Literal["izquierda", "centro", "derecha"] = Field(description="Ubicación ideológica del medio")
    headline: str = Field(description="Titular original del medio")
    angle: str = Field(description="Cómo enfoca o enmarca la noticia este medio (1-2 frases concisas)")
    url: str = Field(description="URL directa al artículo original")


class TopicItem(BaseModel):
    id: int = Field(description="Identificador numérico del tema (1 a 5)")
    category: str = Field(description="Categoría temática (ej. Política, Economía, Sociedad, Internacional, Cultura)")
    neutral_title: str = Field(description="Título neutro, directo y con toque editorial limpio (estilo Kloshletter/Ground News)")
    executive_summary: str = Field(
        description="Resumen ejecutivo de 1 párrafo explicando el contexto, los hechos clave y por qué importa hoy"
    )
    coverage: CoverageDistribution
    blindspot: BlindspotInfo
    perspectives: List[MediaPerspective] = Field(
        description="Lista de medios que cubren este tema con su enfoque y enlace original"
    )


class InternationalRead(BaseModel):
    source_name: str = Field(default="The New Yorker", description="Nombre del medio internacional")
    original_title: str = Field(description="Titular original del artículo")
    translated_title: str = Field(description="Titular traducido o adaptado al español de forma atractiva")
    summary: str = Field(description="Resumen de 2-3 frases explicando de qué trata el reportaje y por qué merece la pena leerlo")
    reading_Reason: str = Field(description="Etiqueta breve de por qué leerlo (ej. 'Perfil en profundidad', 'Análisis geopolítico')")
    url: str = Field(description="URL al artículo original en The New Yorker")


class DailyEdition(BaseModel):
    edition_title: str = Field(description="Un subtítulo editorial breve que resuma el pulso del día")
    daily_briefing: str = Field(
        description="Un saludo y resumen relámpago de 2-3 frases con tono cercano e inteligente (estilo Kloshletter) para abrir el día"
    )
    top_topics: List[TopicItem] = Field(description="Los 5 grandes temas del día en España")
    international_reads: List[InternationalRead] = Field(
        description="Entre 2 y 3 lecturas recomendadas de The New Yorker"
    )


def clean_html(raw_html: str) -> str:
    """Elimina etiquetas HTML básicas y limpia espacios."""
    if not raw_html:
        return ""
    clean = re.sub(r"<[^>]+>", " ", raw_html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:450] + ("..." if len(clean) > 450 else "")


def fetch_kloshletter_fallback(headers: dict) -> list:
    """Fallback para Kloshletter usando rss2json y la API JSON de Substack cuando bloquean las IPs de GitHub Actions."""
    items = []

    # Intento 1: API pública de rss2json
    rss2json_url = "https://api.rss2json.com/v1/api.json?rss_url=https://kloshletter.substack.com/feed"
    try:
        print("   🔄 Probando fallback rss2json para Kloshletter...")
        resp = requests.get(rss2json_url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "ok" and data.get("items"):
            for entry in data["items"][:MAX_ITEMS_PER_FEED]:
                title = (entry.get("title") or "").strip()
                summary = clean_html(entry.get("description") or entry.get("content") or "")
                link = (entry.get("link") or "").strip()
                if title and link:
                    items.append({"title": title, "description": summary, "url": link})
            if items:
                return items
    except Exception as e:
        print(f"   ⚠️ Fallback rss2json falló: {e}")

    # Intento 2: API JSON de Substack
    substack_api_url = "https://kloshletter.substack.com/api/v1/posts?limit=5"
    try:
        print("   🔄 Probando fallback API Substack para Kloshletter...")
        resp = requests.get(substack_api_url, headers=headers, timeout=15)
        resp.raise_for_status()
        posts = resp.json()
        if isinstance(posts, list):
            for post in posts[:MAX_ITEMS_PER_FEED]:
                title = (post.get("title") or "").strip()
                summary = clean_html(post.get("subtitle") or post.get("description") or post.get("truncated_body_text") or "")
                link = (post.get("canonical_url") or "").strip()
                if not link and post.get("slug"):
                    link = f"https://kloshletter.substack.com/p/{post['slug']}"
                if title and link:
                    items.append({"title": title, "description": summary, "url": link})
    except Exception as e:
        print(f"   ⚠️ Fallback API Substack falló: {e}")

    return items


def fetch_rss_items() -> dict:
    """Descarga y parsea los primeros 10 titulares y descripciones de cada medio."""
    collected = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
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
            print(f"⚠️ Aviso: fallo con requests en {source_name} ({e}), reintentando...")
            feed = feedparser.parse(url, request_headers=headers)

        items = []
        if feed and getattr(feed, "entries", None):
            for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
                title = entry.get("title", "").strip()
                summary = clean_html(entry.get("summary", entry.get("description", "")))
                link = entry.get("link", "").strip()
                if title and link:
                    items.append({
                        "title": title,
                        "description": summary,
                        "url": link,
                    })

        if not items and source_name == "Kloshletter":
            items = fetch_kloshletter_fallback(headers)

        collected[source_name] = {
            "bias": meta["bias"],
            "category": meta["category"],
            "items": items,
        }
        print(f"   ✓ {len(items)} artículos obtenidos de {source_name}.")

    return collected


def analyze_with_gemini(rss_data: dict) -> dict:
    """Envía los titulares a Gemini 3.8 Flash y devuelve el JSON estructurado."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: La variable de entorno GEMINI_API_KEY no está definida.", file=sys.stderr)
        print("   Ejecuta: export GEMINI_API_KEY='tu_clave_aqui'", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    prompt = f"""
Eres el editor jefe de un agregador diario de noticias en España que combina la claridad y cercanía de **Kloshletter** con el análisis de sesgo mediático y puntos ciegos de **Ground News**.

A continuación tienes los 10 primeros titulares y descripciones del día extraídos por RSS de varios medios españoles (Kloshletter, El País, elDiario.es, El Mundo, El Salto) y de The New Yorker.

Clasificación de referencia de los medios nacionales:
- **Izquierda**: El País (centro-izquierda/progresista), elDiario.es (izquierda/progresista), El Salto (izquierda alternativa/crítica).
- **Centro / Síntesis**: Kloshletter (boletín generalista de síntesis).
- **Derecha**: El Mundo (centro-derecha/liberal-conservador).

### Tu tarea:
1. **Identifica los 5 grandes temas del día en España** agrupando las noticias relacionadas de los distintos medios nacionales. Si un tema muy relevante solo lo cubre un bloque ideológico, inclúyelo también para evidenciar el *Punto Ciego* (Blindspot).
2. Para cada uno de los 5 temas:
   - Redacta un **título neutro** y periodístico.
   - Escribe un **resumen ejecutivo de 1 párrafo** (con el estilo ágil, riguroso y ameno de Kloshletter, contextualizando qué ha pasado y las distintas aristas).
   - Calcula la **barra visual de cobertura** (`left`, `center`, `right`) cuyos porcentajes deben sumar 100, reflejando el peso de los medios que cubren la noticia.
   - Detalla en `perspectives` **cómo enfoca la noticia cada medio que la cubre**, incluyendo el titular original y el enlace exacto (`url`) proporcionado en los datos de entrada. No inventes URLs.
   - Determina el indicador de **Punto Ciego (`blindspot`)**:
     - Si el tema es cubierto exclusivamente (o casi exclusivamente) por la izquierda y omitido por El Mundo (derecha), marca `has_blindspot: true` e `ignored_by: "derecha"`.
     - Si el tema es impulsado por El Mundo (derecha) y omitido por los medios de izquierda (El País, elDiario.es, El Salto), marca `has_blindspot: true` e `ignored_by: "izquierda"`.
     - Explica brevemente en `explanation` por qué hay punto ciego o qué enfoque falta.
3. **Sección Internacional (The New Yorker)**:
   - Selecciona entre **2 y 3 lecturas recomendadas** de los artículos de *The New Yorker*.
   - Traduce su titular al español, escribe un resumen atractivo en español de 2-3 frases explicando por qué merece una lectura pausada y conserva su URL original.

Datos RSS de entrada (JSON):
{json.dumps(rss_data, ensure_ascii=False, indent=2)}
"""

    print("🧠 Analizando noticias y sesgos con Gemini (gemini-3.8-flash)...")
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=DailyEdition,
            temperature=0.3,
        ),
    )

    result = json.loads(response.text)
    return result


def main():
    rss_data = fetch_rss_items()
    edition_data = analyze_with_gemini(rss_data)

    # Añadir metadatos de fecha y fuentes
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

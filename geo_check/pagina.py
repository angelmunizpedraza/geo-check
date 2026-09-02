"""Análisis de una página HTML desde el punto de vista de un modelo generativo.

Un LLM que resume o cita una página necesita tres cosas: saber qué es
(datos estructurados), poder leerla (texto real, no solo JavaScript) y
encontrar respuestas directas (encabezados y párrafos que respondan preguntas).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

# Tipos schema.org que más ayudan a un modelo a entender y citar el contenido.
TIPOS_VALIOSOS = {
    "Organization", "LocalBusiness", "WebSite", "WebPage", "Article",
    "NewsArticle", "BlogPosting", "FAQPage", "HowTo", "Course", "Product",
    "Service", "Person", "BreadcrumbList", "Event", "Review",
}

# Campos que, si faltan, dejan el tipo a medias.
CAMPOS_ESPERADOS = {
    "Organization": ["name", "url"],
    "LocalBusiness": ["name", "address", "telephone"],
    "Article": ["headline", "author", "datePublished"],
    "BlogPosting": ["headline", "author", "datePublished"],
    "FAQPage": ["mainEntity"],
    "Course": ["name", "description", "provider"],
    "Product": ["name", "description", "offers"],
    "HowTo": ["name", "step"],
}

RE_PREGUNTA = re.compile(r"^(qué|que|cómo|como|cuánto|cuanto|por qué|porque|dónde|donde|cuál|cual|quién|quien|"
                         r"what|how|why|when|where|which|who)\b", re.I)


@dataclass
class AnalisisPagina:
    url: str
    problemas: list[str] = field(default_factory=list)
    tipos_jsonld: list[str] = field(default_factory=list)
    jsonld_invalidos: int = 0
    campos_faltantes: dict[str, list[str]] = field(default_factory=dict)
    ratio_texto: float = 0.0
    palabras: int = 0
    h1: str | None = None
    h2: list[str] = field(default_factory=list)
    preguntas_en_h2: int = 0
    tiene_faq: bool = False
    lang: str | None = None
    og_completo: bool = False
    fecha_publicacion: str | None = None
    puntuacion: int = 0


def _extraer_tipos(obj, acumulado: list[str]) -> None:
    """Los JSON-LD pueden venir anidados o en @graph; recorremos todo."""
    if isinstance(obj, dict):
        t = obj.get("@type")
        if isinstance(t, str):
            acumulado.append(t)
        elif isinstance(t, list):
            acumulado.extend(x for x in t if isinstance(x, str))
        for v in obj.values():
            _extraer_tipos(v, acumulado)
    elif isinstance(obj, list):
        for x in obj:
            _extraer_tipos(x, acumulado)


def _objetos_por_tipo(obj, acumulado: dict[str, list[dict]]) -> None:
    if isinstance(obj, dict):
        t = obj.get("@type")
        tipos = [t] if isinstance(t, str) else (t if isinstance(t, list) else [])
        for tipo in tipos:
            acumulado.setdefault(tipo, []).append(obj)
        for v in obj.values():
            _objetos_por_tipo(v, acumulado)
    elif isinstance(obj, list):
        for x in obj:
            _objetos_por_tipo(x, acumulado)


def analizar_pagina(url: str, html: str) -> AnalisisPagina:
    a = AnalisisPagina(url=url)
    soup = BeautifulSoup(html, "html.parser")

    # --- idioma y metadatos sociales ----------------------------------------
    html_tag = soup.find("html")
    a.lang = (html_tag.get("lang") or "").strip() or None if html_tag else None
    if not a.lang:
        a.problemas.append("AVISO: falta el atributo lang en <html>; el modelo tiene que adivinar el idioma")

    og = {m.get("property"): m.get("content") for m in soup.find_all("meta", property=True)}
    a.og_completo = bool(og.get("og:title") and og.get("og:description"))
    if not a.og_completo:
        a.problemas.append("AVISO: faltan og:title / og:description; muchos agentes los usan como resumen")

    # --- datos estructurados -------------------------------------------------
    por_tipo: dict[str, list[dict]] = {}
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            datos = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            a.jsonld_invalidos += 1
            continue
        _extraer_tipos(datos, a.tipos_jsonld)
        _objetos_por_tipo(datos, por_tipo)

        # fecha de publicación: señal de frescura para el modelo
        if isinstance(datos, dict):
            a.fecha_publicacion = a.fecha_publicacion or datos.get("datePublished") or datos.get("dateModified")

    if a.jsonld_invalidos:
        a.problemas.append(f"ERROR: {a.jsonld_invalidos} bloque(s) JSON-LD con sintaxis inválida")
    if not a.tipos_jsonld:
        a.problemas.append("ERROR: sin datos estructurados JSON-LD; el modelo no sabe qué es esta página")
    elif not any(t in TIPOS_VALIOSOS for t in a.tipos_jsonld):
        a.problemas.append(f"AVISO: los tipos JSON-LD ({', '.join(set(a.tipos_jsonld))}) no describen la entidad principal")

    for tipo, esperados in CAMPOS_ESPERADOS.items():
        for obj in por_tipo.get(tipo, []):
            faltan = [c for c in esperados if not obj.get(c)]
            if faltan:
                a.campos_faltantes.setdefault(tipo, []).extend(faltan)
    for tipo, faltan in a.campos_faltantes.items():
        a.problemas.append(f"AVISO: {tipo} sin {', '.join(sorted(set(faltan)))}")

    a.tiene_faq = "FAQPage" in a.tipos_jsonld

    # --- legibilidad ---------------------------------------------------------
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    texto = soup.get_text(" ", strip=True)
    a.palabras = len(texto.split())
    a.ratio_texto = round(len(texto) / max(len(html), 1), 3)

    if a.palabras < 150:
        a.problemas.append(f"ERROR: solo {a.palabras} palabras visibles; si el contenido carga con JavaScript, el modelo no lo verá")
    if a.ratio_texto < 0.08:
        a.problemas.append(f"AVISO: ratio texto/HTML de {a.ratio_texto:.0%}; demasiado código para tan poco contenido")

    # --- estructura de respuesta --------------------------------------------
    h1 = soup.find("h1")
    a.h1 = h1.get_text(strip=True) if h1 else None
    if not a.h1:
        a.problemas.append("AVISO: sin H1; el modelo no tiene un tema claro para la página")

    a.h2 = [h.get_text(strip=True) for h in soup.find_all("h2")]
    a.preguntas_en_h2 = sum(1 for h in a.h2 if RE_PREGUNTA.match(h) or h.endswith("?"))
    if len(a.h2) < 2 and a.palabras > 400:
        a.problemas.append("AVISO: texto largo con menos de dos H2; sin secciones el modelo no puede citar fragmentos")

    a.puntuacion = _puntuar(a)
    return a


def _puntuar(a: AnalisisPagina) -> int:
    """0-100. Pesos: qué es la página (40), si se puede leer (30), si responde (30)."""
    pts = 0
    # entidad
    if a.tipos_jsonld and not a.jsonld_invalidos:
        pts += 20
        if any(t in TIPOS_VALIOSOS for t in a.tipos_jsonld):
            pts += 10
        if not a.campos_faltantes:
            pts += 10
    # legibilidad
    if a.palabras >= 150:
        pts += 15
    if a.ratio_texto >= 0.08:
        pts += 10
    if a.lang:
        pts += 5
    # respuesta
    if a.h1:
        pts += 10
    if len(a.h2) >= 2:
        pts += 8
    if a.preguntas_en_h2 or a.tiene_faq:
        pts += 7
    if a.og_completo:
        pts += 5
    return min(pts, 100)

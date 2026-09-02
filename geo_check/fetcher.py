"""Descarga de recursos del sitio y análisis de acceso para rastreadores de IA."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests

USER_AGENT = "geo-check/1.0 (+https://github.com/angelmunizpedraza/geo-check)"

# Rastreadores de IA relevantes en 2026 y quién los opera.
# Bloquearlos en robots.txt significa no aparecer en sus respuestas.
BOTS_IA = {
    "GPTBot": "OpenAI (entrenamiento)",
    "OAI-SearchBot": "OpenAI (búsqueda en ChatGPT)",
    "ChatGPT-User": "OpenAI (navegación en tiempo real)",
    "ClaudeBot": "Anthropic",
    "anthropic-ai": "Anthropic (legado)",
    "PerplexityBot": "Perplexity",
    "Google-Extended": "Google (Gemini / AI Overviews)",
    "Applebot-Extended": "Apple Intelligence",
    "CCBot": "Common Crawl (base de muchos modelos)",
    "Bytespider": "ByteDance",
    "meta-externalagent": "Meta AI",
}


@dataclass
class Recurso:
    url: str
    status: int
    texto: str = ""
    content_type: str = ""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and not self.error


@dataclass
class AccesoBots:
    """Resultado de leer robots.txt desde el punto de vista de los bots de IA."""

    existe: bool
    bloqueados: dict[str, str] = field(default_factory=dict)   # bot -> operador
    permitidos: dict[str, str] = field(default_factory=dict)
    bloqueo_total: bool = False  # User-agent: * / Disallow: /


class Fetcher:
    def __init__(self, base_url: str, timeout: int = 15):
        parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
        self.base = f"{parsed.scheme}://{parsed.netloc}"
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def get(self, ruta_o_url: str) -> Recurso:
        url = urljoin(self.base + "/", ruta_o_url)
        try:
            r = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if "charset" not in r.headers.get("Content-Type", "").lower():
                r.encoding = r.apparent_encoding or "utf-8"
            return Recurso(url=r.url, status=r.status_code, texto=r.text,
                           content_type=r.headers.get("Content-Type", ""))
        except requests.RequestException as exc:
            return Recurso(url=url, status=0, error=str(exc))

    def robots(self) -> AccesoBots:
        rec = self.get("/robots.txt")
        if not rec.ok:
            return AccesoBots(existe=False)
        return analizar_robots(rec.texto)


def analizar_robots(texto: str) -> AccesoBots:
    """Interpreta robots.txt grupo a grupo.

    Un grupo empieza con una o varias líneas User-agent y sigue con sus
    directivas. Solo nos importa si cada bot de IA tiene un 'Disallow: /'
    aplicable, ya sea en su propio grupo o heredado del comodín.
    """
    grupos: list[tuple[list[str], list[str]]] = []
    agentes_actuales: list[str] = []
    directivas_actuales: list[str] = []
    leyendo_agentes = False

    for linea in texto.splitlines():
        linea = linea.split("#", 1)[0].strip()
        if not linea or ":" not in linea:
            continue
        clave, valor = (x.strip() for x in linea.split(":", 1))
        clave = clave.lower()

        if clave == "user-agent":
            if not leyendo_agentes and agentes_actuales:
                grupos.append((agentes_actuales, directivas_actuales))
                agentes_actuales, directivas_actuales = [], []
            agentes_actuales.append(valor.lower())
            leyendo_agentes = True
        elif clave in ("disallow", "allow"):
            directivas_actuales.append(f"{clave}:{valor}")
            leyendo_agentes = False

    if agentes_actuales:
        grupos.append((agentes_actuales, directivas_actuales))

    def bloquea_todo(directivas: list[str]) -> bool:
        return "disallow:/" in directivas and "allow:/" not in directivas

    comodin = next((d for a, d in grupos if "*" in a), None)
    bloqueo_total = bloquea_todo(comodin) if comodin else False

    resultado = AccesoBots(existe=True, bloqueo_total=bloqueo_total)
    for bot, operador in BOTS_IA.items():
        propio = next((d for a, d in grupos if bot.lower() in a), None)
        if propio is not None:
            bloqueado = bloquea_todo(propio)
        else:
            bloqueado = bloqueo_total
        (resultado.bloqueados if bloqueado else resultado.permitidos)[bot] = operador
    return resultado

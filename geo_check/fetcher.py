"""Descarga de recursos del sitio y análisis de acceso para rastreadores de IA."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests

USER_AGENT = "geo-check/1.0 (+https://github.com/angelmunizpedraza/geo-check)"

# Rastreadores de IA relevantes en 2026, agrupados por el motor al que alimentan.
#
# La distinción que importa: un bot de CITA recupera la página en el momento de
# responder y es el que puede citarte; un bot de ENTRENAMIENTO solo alimenta el
# modelo. Bloquear GPTBot (entrenamiento de OpenAI) y bloquear Google-Extended
# (AI Overviews) son dos problemas distintos y no deben promediarse en una cifra.
#
# peso = importancia del motor para la visibilidad en respuestas de IA (suma 25).
MOTORES: dict[str, dict] = {
    "ChatGPT (OpenAI)": {
        "peso": 8,
        "bots": {
            "OAI-SearchBot": "cita",           # índice de búsqueda de ChatGPT
            "ChatGPT-User": "cita",            # navegación en tiempo real
            "GPTBot": "entrenamiento",
        },
    },
    "Google AI Overviews / Gemini": {
        "peso": 6,
        "bots": {
            "Google-Extended": "entrenamiento",  # controla el uso en Gemini y AI Overviews
        },
    },
    "Perplexity": {
        "peso": 5,
        "bots": {
            "PerplexityBot": "cita",
        },
    },
    "Claude (Anthropic)": {
        "peso": 3,
        "bots": {
            "Claude-SearchBot": "cita",
            "ClaudeBot": "entrenamiento",
            "anthropic-ai": "entrenamiento",
        },
    },
    "Apple Intelligence": {"peso": 1, "bots": {"Applebot-Extended": "entrenamiento"}},
    "Meta AI": {"peso": 1, "bots": {"meta-externalagent": "entrenamiento"}},
    "Common Crawl (base de muchos modelos)": {"peso": 1, "bots": {"CCBot": "entrenamiento"}},
}

# bot -> operador (mantiene la interfaz anterior)
BOTS_IA = {
    bot: motor
    for motor, cfg in MOTORES.items()
    for bot in cfg["bots"]
}

# bot -> "cita" | "entrenamiento"
ROL_BOT = {
    bot: rol
    for cfg in MOTORES.values()
    for bot, rol in cfg["bots"].items()
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
class AccesoMotor:
    """Acceso de un motor concreto, separando bots de cita y de entrenamiento."""

    motor: str
    peso: int
    bloqueados: dict[str, str] = field(default_factory=dict)   # bot -> rol
    permitidos: dict[str, str] = field(default_factory=dict)

    @property
    def bots_cita(self) -> list[str]:
        return [b for b, rol in {**self.permitidos, **self.bloqueados}.items() if rol == "cita"]

    @property
    def cita_bloqueada(self) -> bool:
        """No puede citarte: todos sus bots de recuperación en vivo están bloqueados."""
        cita = self.bots_cita
        return bool(cita) and all(b in self.bloqueados for b in cita)

    @property
    def estado(self) -> str:
        if not self.bloqueados:
            return "abierto"
        if not self.permitidos:
            return "bloqueado"
        return "parcial"

    @property
    def puntos(self) -> float:
        """Del peso del motor: 0 si está cerrado, la mitad si solo entra a entrenar."""
        if not self.bloqueados:
            return float(self.peso)
        if not self.permitidos:
            return 0.0
        # Los bots de cita valen el doble que los de entrenamiento dentro del motor.
        def valor(bot: str, rol: str) -> int:
            return 2 if rol == "cita" else 1
        total = sum(valor(b, r) for b, r in {**self.permitidos, **self.bloqueados}.items())
        abierto = sum(valor(b, r) for b, r in self.permitidos.items())
        return round(self.peso * abierto / total, 2) if total else 0.0


@dataclass
class AccesoBots:
    """Resultado de leer robots.txt desde el punto de vista de los bots de IA."""

    existe: bool
    bloqueados: dict[str, str] = field(default_factory=dict)   # bot -> operador
    permitidos: dict[str, str] = field(default_factory=dict)
    bloqueo_total: bool = False  # User-agent: * / Disallow: /
    motores: dict[str, AccesoMotor] = field(default_factory=dict)

    @property
    def puntos_acceso(self) -> int:
        """0-25 ponderado por motor, no por número de bots."""
        return round(sum(m.puntos for m in self.motores.values()))

    @property
    def motores_sin_cita(self) -> list[str]:
        """Motores que directamente no pueden citarte."""
        return [n for n, m in self.motores.items() if m.cita_bloqueada]


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
    for motor, cfg in MOTORES.items():
        am = AccesoMotor(motor=motor, peso=cfg["peso"])
        for bot, rol in cfg["bots"].items():
            propio = next((d for a, d in grupos if bot.lower() in a), None)
            bloqueado = bloquea_todo(propio) if propio is not None else bloqueo_total
            if bloqueado:
                am.bloqueados[bot] = rol
                resultado.bloqueados[bot] = motor
            else:
                am.permitidos[bot] = rol
                resultado.permitidos[bot] = motor
        resultado.motores[motor] = am
    return resultado

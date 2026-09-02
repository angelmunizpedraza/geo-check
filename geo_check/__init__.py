"""geo-check: auditoría de preparación para buscadores generativos."""

__version__ = "1.0.0"

from .fetcher import Fetcher, analizar_robots, BOTS_IA
from .llms import validar_llms, generar_llms
from .pagina import analizar_pagina

__all__ = ["Fetcher", "analizar_robots", "BOTS_IA", "validar_llms", "generar_llms", "analizar_pagina"]

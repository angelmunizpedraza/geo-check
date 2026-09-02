"""Validación del archivo llms.txt.

El formato (llmstxt.org) es Markdown con una estructura fija:

    # Nombre del sitio
    > Resumen de una o dos frases.
    Texto libre opcional.
    ## Sección
    - [Título](https://url): descripción opcional
    ## Optional
    - [Recursos secundarios](https://url)

Los modelos lo usan para saber qué leer primero. Un llms.txt roto o vacío
es peor que no tenerlo: el modelo lo intenta y descarta el sitio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

RE_ENLACE = re.compile(r"^\s*[-*]\s*\[([^\]]+)\]\((https?://[^)\s]+)\)(?::\s*(.*))?$")


@dataclass
class ResultadoLlms:
    existe: bool
    titulo: str | None = None
    resumen: str | None = None
    secciones: dict[str, list[dict]] = field(default_factory=dict)
    problemas: list[str] = field(default_factory=list)
    total_enlaces: int = 0

    @property
    def valido(self) -> bool:
        return self.existe and self.titulo is not None and not any(
            p.startswith("ERROR") for p in self.problemas
        )


def validar_llms(texto: str | None) -> ResultadoLlms:
    if texto is None:
        return ResultadoLlms(existe=False, problemas=["ERROR: no existe /llms.txt"])

    res = ResultadoLlms(existe=True)
    lineas = texto.splitlines()

    # 1. Título: primera línea no vacía debe ser un H1
    primera = next((ln for ln in lineas if ln.strip()), "")
    if primera.startswith("# "):
        res.titulo = primera[2:].strip()
    else:
        res.problemas.append("ERROR: la primera línea debe ser un título H1 ('# Nombre')")

    # 2. Resumen en blockquote justo después del título
    idx_titulo = next((i for i, ln in enumerate(lineas) if ln.startswith("# ")), -1)
    for ln in lineas[idx_titulo + 1:]:
        if not ln.strip():
            continue
        if ln.startswith(">"):
            res.resumen = ln.lstrip("> ").strip()
        break
    if not res.resumen:
        res.problemas.append("AVISO: falta el resumen en blockquote ('> ...') tras el título")
    elif len(res.resumen) < 40:
        res.problemas.append("AVISO: el resumen es muy corto; describe qué ofrece el sitio")

    # 3. Secciones H2 con listas de enlaces
    seccion_actual: str | None = None
    for ln in lineas:
        if ln.startswith("## "):
            seccion_actual = ln[3:].strip()
            res.secciones.setdefault(seccion_actual, [])
            continue
        m = RE_ENLACE.match(ln)
        if m and seccion_actual:
            res.secciones[seccion_actual].append({
                "titulo": m.group(1).strip(),
                "url": m.group(2).strip(),
                "descripcion": (m.group(3) or "").strip(),
            })
            res.total_enlaces += 1
        elif ln.strip().startswith(("-", "*")) and seccion_actual and "](" in ln:
            res.problemas.append(f"AVISO: enlace mal formado en '{seccion_actual}': {ln.strip()[:60]}")

    if not res.secciones:
        res.problemas.append("ERROR: no hay secciones '## ' con enlaces")
    else:
        vacias = [s for s, e in res.secciones.items() if not e]
        for s in vacias:
            res.problemas.append(f"AVISO: la sección '{s}' no tiene enlaces")

    if res.total_enlaces == 0 and res.secciones:
        res.problemas.append("ERROR: ninguna sección contiene enlaces válidos")

    sin_desc = sum(1 for e in res.secciones.values() for x in e if not x["descripcion"])
    if res.total_enlaces and sin_desc / res.total_enlaces > 0.5:
        res.problemas.append(
            f"AVISO: {sin_desc} de {res.total_enlaces} enlaces sin descripción; "
            "la descripción es lo que el modelo usa para decidir qué abrir"
        )

    return res


def generar_llms(nombre: str, resumen: str, secciones: dict[str, list[tuple[str, str, str]]]) -> str:
    """Genera un llms.txt válido a partir de datos estructurados.

    secciones: {"Cursos": [("Título", "https://url", "descripción"), ...]}
    """
    partes = [f"# {nombre}", "", f"> {resumen}", ""]
    for nombre_sec, enlaces in secciones.items():
        partes.append(f"## {nombre_sec}")
        partes.append("")
        for titulo, url, desc in enlaces:
            partes.append(f"- [{titulo}]({url})" + (f": {desc}" if desc else ""))
        partes.append("")
    return "\n".join(partes).rstrip() + "\n"

"""CLI: python -m geo_check https://ejemplo.com [url2 url3 ...]"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from .fetcher import Fetcher, BOTS_IA
from .llms import validar_llms
from .pagina import analizar_pagina, AnalisisPagina


def _barra(n: int, ancho: int = 20) -> str:
    llenos = round(n / 100 * ancho)
    return "█" * llenos + "░" * (ancho - llenos)


def ejecutar(base_url: str, urls_extra: list[str], quiet: bool = False) -> dict:
    f = Fetcher(base_url)
    salida: dict = {"sitio": f.base, "generado": datetime.now().isoformat(timespec="seconds")}

    # 1. Acceso de rastreadores de IA
    acceso = f.robots()
    salida["robots"] = {
        "existe": acceso.existe,
        "bloqueo_total": acceso.bloqueo_total,
        "bloqueados": acceso.bloqueados,
        "permitidos": acceso.permitidos,
    }

    # 2. llms.txt
    rec = f.get("/llms.txt")
    llms = validar_llms(rec.texto if rec.ok and "html" not in rec.content_type.lower() else None)
    salida["llms_txt"] = {
        "existe": llms.existe,
        "valido": llms.valido,
        "titulo": llms.titulo,
        "secciones": {k: len(v) for k, v in llms.secciones.items()},
        "total_enlaces": llms.total_enlaces,
        "problemas": llms.problemas,
    }
    rec_full = f.get("/llms-full.txt")
    salida["llms_full_txt"] = rec_full.ok and "html" not in rec_full.content_type.lower()

    # 3. Páginas
    urls = [f.base + "/"] + urls_extra
    paginas: list[AnalisisPagina] = []
    for u in urls:
        r = f.get(u)
        if not r.ok:
            paginas.append(AnalisisPagina(url=u, problemas=[f"ERROR: HTTP {r.status} {r.error or ''}".strip()]))
            continue
        paginas.append(analizar_pagina(r.url, r.texto))
    salida["paginas"] = [vars(p) for p in paginas]

    # 4. Puntuación global
    media_paginas = round(sum(p.puntuacion for p in paginas) / len(paginas)) if paginas else 0
    pts_acceso = 0 if acceso.bloqueo_total else (25 if len(acceso.bloqueados) <= 2 else 12)
    pts_llms = 20 if llms.valido else (8 if llms.existe else 0)
    salida["puntuacion"] = {
        "acceso_bots": pts_acceso,       # de 25
        "llms_txt": pts_llms,            # de 20
        "paginas": round(media_paginas * 0.55),  # de 55
    }
    salida["puntuacion"]["total"] = sum(salida["puntuacion"].values())

    if not quiet:
        imprimir(salida, acceso, llms, paginas)
    return salida


def imprimir(salida: dict, acceso, llms, paginas: list[AnalisisPagina]) -> None:
    total = salida["puntuacion"]["total"]
    print("\n" + "=" * 68)
    print(f"GEO CHECK · {salida['sitio']}")
    print("=" * 68)
    print(f"\nPuntuación global  {_barra(total)}  {total}/100")
    p = salida["puntuacion"]
    print(f"  Acceso de bots IA   {p['acceso_bots']:>3}/25")
    print(f"  llms.txt            {p['llms_txt']:>3}/20")
    print(f"  Páginas             {p['paginas']:>3}/55")

    print("\n── Rastreadores de IA (robots.txt) ──")
    if not acceso.existe:
        print("  Sin robots.txt: todos los bots pueden entrar (y también los que no quieres).")
    elif acceso.bloqueo_total:
        print("  BLOQUEO TOTAL: 'User-agent: *' con 'Disallow: /'. Ningún modelo verá el sitio.")
    else:
        if acceso.bloqueados:
            print("  Bloqueados:")
            for bot, op in acceso.bloqueados.items():
                print(f"    ✗ {bot:<20} {op}")
        print(f"  Permitidos: {len(acceso.permitidos)} de {len(BOTS_IA)}")

    print("\n── llms.txt ──")
    if not llms.existe:
        print("  No existe. Es el primer archivo que un modelo busca para orientarse en el sitio.")
    else:
        estado = "válido" if llms.valido else "con errores"
        print(f"  Existe y es {estado}. Título: '{llms.titulo}'. "
              f"{len(llms.secciones)} secciones, {llms.total_enlaces} enlaces.")
        for prob in llms.problemas:
            print(f"    · {prob}")
    print(f"  llms-full.txt: {'sí' if salida['llms_full_txt'] else 'no'}")

    print("\n── Páginas ──")
    for pg in paginas:
        print(f"\n  {pg.url}")
        print(f"  {_barra(pg.puntuacion, 16)} {pg.puntuacion}/100")
        if pg.tipos_jsonld:
            print(f"    JSON-LD: {', '.join(sorted(set(pg.tipos_jsonld)))}")
        if pg.palabras:
            print(f"    {pg.palabras} palabras · ratio texto {pg.ratio_texto:.0%} · "
                  f"{len(pg.h2)} H2 ({pg.preguntas_en_h2} en forma de pregunta)")
        for prob in pg.problemas:
            print(f"    · {prob}")
    print()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="geo-check",
        description="Comprueba si un sitio está preparado para buscadores generativos (ChatGPT, Perplexity, AI Overviews).",
    )
    parser.add_argument("url", help="URL del sitio, por ejemplo https://ejemplo.com")
    parser.add_argument("paginas", nargs="*", help="URLs adicionales a analizar")
    parser.add_argument("--json", metavar="RUTA", help="guardar resultado en JSON")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args(argv)

    resultado = ejecutar(args.url, args.paginas, quiet=args.quiet)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(resultado, fh, ensure_ascii=False, indent=2, default=str)
        print(f"JSON guardado en {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

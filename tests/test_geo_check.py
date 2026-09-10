import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from geo_check.fetcher import analizar_robots  # noqa: E402
from geo_check.llms import validar_llms, generar_llms  # noqa: E402
from geo_check.pagina import analizar_pagina  # noqa: E402


# --- robots.txt --------------------------------------------------------------

def test_robots_vacio_permite_todo():
    r = analizar_robots("")
    assert r.existe and not r.bloqueados and not r.bloqueo_total


def test_bloqueo_especifico_de_gptbot():
    r = analizar_robots("User-agent: GPTBot\nDisallow: /\n")
    assert "GPTBot" in r.bloqueados
    assert "ClaudeBot" in r.permitidos


def test_bloqueo_total_afecta_a_todos():
    r = analizar_robots("User-agent: *\nDisallow: /\n")
    assert r.bloqueo_total
    assert len(r.permitidos) == 0


def test_excepcion_al_bloqueo_total():
    """Caso real: bloquear todo salvo un bot concreto."""
    txt = "User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nAllow: /\n"
    r = analizar_robots(txt)
    assert r.bloqueo_total
    assert "GPTBot" in r.permitidos
    assert "ClaudeBot" in r.bloqueados


def test_varios_agentes_en_un_grupo():
    txt = "User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /\n"
    r = analizar_robots(txt)
    assert {"GPTBot", "ClaudeBot"} <= set(r.bloqueados)
    assert "PerplexityBot" in r.permitidos


def test_disallow_parcial_no_es_bloqueo():
    """Disallow: /admin no bloquea el sitio, solo una ruta."""
    r = analizar_robots("User-agent: *\nDisallow: /admin\n")
    assert not r.bloqueo_total
    assert not r.bloqueados


def test_comentarios_y_mayusculas_se_ignoran():
    txt = "# bloqueo de IA\nUSER-AGENT: gptbot\nDISALLOW: /   # todo\n"
    r = analizar_robots(txt)
    assert "GPTBot" in r.bloqueados


# --- llms.txt ----------------------------------------------------------------

LLMS_OK = """# Academia Ejemplo

> Formación online en criminalística con titulación propia y tutorías personalizadas.

## Cursos

- [Perito judicial](https://ejemplo.com/perito): curso de 300 horas con prácticas
- [Criminología](https://ejemplo.com/criminologia): máster de un año

## Optional

- [Blog](https://ejemplo.com/blog)
"""


def test_llms_valido():
    r = validar_llms(LLMS_OK)
    assert r.valido
    assert r.titulo == "Academia Ejemplo"
    assert r.total_enlaces == 3
    assert set(r.secciones) == {"Cursos", "Optional"}


def test_llms_inexistente():
    r = validar_llms(None)
    assert not r.existe and not r.valido


def test_llms_sin_titulo_h1_es_error():
    r = validar_llms("Academia\n> resumen largo de más de cuarenta caracteres aquí\n## S\n- [a](https://x.com)")
    assert not r.valido
    assert any("H1" in p for p in r.problemas)


def test_llms_sin_resumen_es_aviso_no_error():
    r = validar_llms("# T\n## S\n- [a](https://x.com): d\n")
    assert r.valido
    assert any("blockquote" in p for p in r.problemas)


def test_llms_sin_secciones_es_error():
    r = validar_llms("# T\n> resumen suficientemente largo para no dar aviso extra\n")
    assert not r.valido


def test_llms_enlace_mal_formado_se_reporta():
    r = validar_llms("# T\n> resumen suficientemente largo para no dar aviso extra\n## S\n- [a](ftp://x)\n- [b](https://ok.com): bien\n")
    assert r.total_enlaces == 1
    assert any("mal formado" in p for p in r.problemas)


def test_llms_mayoria_sin_descripcion_avisa():
    txt = "# T\n> resumen suficientemente largo para no dar aviso extra\n## S\n" + \
          "\n".join(f"- [a{i}](https://x.com/{i})" for i in range(4))
    r = validar_llms(txt)
    assert any("sin descripción" in p for p in r.problemas)


def test_generar_y_validar_ida_y_vuelta():
    txt = generar_llms("Sitio", "Un resumen razonablemente largo para describir el sitio.",
                       {"Guías": [("Guía A", "https://s.com/a", "desc"), ("Guía B", "https://s.com/b", "")]})
    r = validar_llms(txt)
    assert r.valido and r.total_enlaces == 2


# --- página ------------------------------------------------------------------

def pagina_html(head="", body="", lang="es"):
    return f"<!DOCTYPE html><html lang='{lang}'><head>{head}</head><body>{body}</body></html>"


CUERPO_RICO = "<h1>Curso de perito judicial</h1>" + \
    "".join(f"<h2>{h}</h2><p>{'texto ' * 60}</p>" for h in
            ["Qué es un perito judicial", "Cuánto dura el curso", "Salidas profesionales"])

JSONLD_COURSE = ('<script type="application/ld+json">{"@context":"https://schema.org","@type":"Course",'
                 '"name":"Perito","description":"Curso","provider":{"@type":"Organization","name":"Academia"}}</script>')
OG = '<meta property="og:title" content="Perito"><meta property="og:description" content="Curso online">'


def test_pagina_completa_puntua_alto():
    a = analizar_pagina("https://x.com/", pagina_html(head=JSONLD_COURSE + OG, body=CUERPO_RICO))
    assert a.puntuacion >= 90
    assert "Course" in a.tipos_jsonld and "Organization" in a.tipos_jsonld
    assert a.preguntas_en_h2 == 2


def test_pagina_vacia_puntua_bajo():
    a = analizar_pagina("https://x.com/", pagina_html(body="<div id='app'></div>", lang=""))
    assert a.puntuacion < 20
    assert any("JavaScript" in p for p in a.problemas)
    assert any("lang" in p for p in a.problemas)


def test_jsonld_invalido_se_cuenta():
    a = analizar_pagina("https://x.com/", pagina_html(head='<script type="application/ld+json">{x</script>', body=CUERPO_RICO))
    assert a.jsonld_invalidos == 1
    assert any("inválida" in p for p in a.problemas)


def test_campos_faltantes_en_course():
    head = '<script type="application/ld+json">{"@type":"Course","name":"Perito"}</script>'
    a = analizar_pagina("https://x.com/", pagina_html(head=head, body=CUERPO_RICO))
    assert set(a.campos_faltantes["Course"]) == {"description", "provider"}


def test_graph_anidado_se_recorre():
    head = ('<script type="application/ld+json">{"@context":"https://schema.org","@graph":['
            '{"@type":"WebSite","name":"S"},{"@type":"Organization","name":"O","url":"https://x.com"}]}</script>')
    a = analizar_pagina("https://x.com/", pagina_html(head=head, body=CUERPO_RICO))
    assert {"WebSite", "Organization"} <= set(a.tipos_jsonld)


def test_faqpage_cuenta_como_respuesta():
    head = '<script type="application/ld+json">{"@type":"FAQPage","mainEntity":[]}</script>'
    a = analizar_pagina("https://x.com/", pagina_html(head=head, body="<h1>T</h1><p>" + "palabra " * 200 + "</p>"))
    assert a.tiene_faq


def test_scripts_no_cuentan_como_texto():
    body = "<h1>T</h1><p>hola mundo</p><script>" + "var x = 1;" * 500 + "</script>"
    a = analizar_pagina("https://x.com/", pagina_html(body=body))
    assert a.palabras < 10


# ── Desglose por motor (v0.2): bloquear GPTBot y bloquear Google-Extended
# ── son problemas distintos y no deben promediarse en una sola cifra.

def test_motores_separan_chatgpt_de_google():
    r = analizar_robots("User-agent: GPTBot\nDisallow: /\n")
    chatgpt = r.motores["ChatGPT (OpenAI)"]
    google = r.motores["Google AI Overviews / Gemini"]
    assert chatgpt.estado == "parcial" and "GPTBot" in chatgpt.bloqueados
    assert google.estado == "abierto"
    # ChatGPT pierde puntos, Google conserva los suyos íntegros
    assert chatgpt.puntos < chatgpt.peso and google.puntos == google.peso


def test_bloquear_entrenamiento_no_impide_la_cita():
    """GPTBot bloqueado pero OAI-SearchBot permitido: ChatGPT todavía puede citarte."""
    r = analizar_robots("User-agent: GPTBot\nDisallow: /\n")
    assert r.motores["ChatGPT (OpenAI)"].cita_bloqueada is False
    assert r.motores_sin_cita == []


def test_bloquear_los_bots_de_cita_si_lo_impide():
    txt = "User-agent: OAI-SearchBot\nDisallow: /\n\nUser-agent: ChatGPT-User\nDisallow: /\n"
    r = analizar_robots(txt)
    assert r.motores["ChatGPT (OpenAI)"].cita_bloqueada is True
    assert "ChatGPT (OpenAI)" in r.motores_sin_cita
    # pero el entrenamiento sigue abierto: no es un bloqueo total
    assert r.motores["ChatGPT (OpenAI)"].estado == "parcial"


def test_perplexity_bloqueado_no_puede_citarte():
    r = analizar_robots("User-agent: PerplexityBot\nDisallow: /\n")
    assert r.motores["Perplexity"].estado == "bloqueado"
    assert r.motores["Perplexity"].puntos == 0
    assert "Perplexity" in r.motores_sin_cita


def test_puntuacion_de_acceso_pondera_por_motor_no_por_numero_de_bots():
    """Bloquear ChatGPT entero (3 bots, peso 8) duele más que bloquear 3 motores menores (peso 1 c/u)."""
    solo_chatgpt = analizar_robots(
        "User-agent: GPTBot\nUser-agent: OAI-SearchBot\nUser-agent: ChatGPT-User\nDisallow: /\n"
    )
    tres_menores = analizar_robots(
        "User-agent: Applebot-Extended\nUser-agent: meta-externalagent\nUser-agent: CCBot\nDisallow: /\n"
    )
    assert len(solo_chatgpt.bloqueados) == len(tres_menores.bloqueados) == 3
    assert solo_chatgpt.puntos_acceso < tres_menores.puntos_acceso
    assert solo_chatgpt.puntos_acceso == 25 - 8 and tres_menores.puntos_acceso == 25 - 3


def test_sin_bloqueos_puntuacion_maxima_y_bloqueo_total_cero():
    assert analizar_robots("User-agent: *\nAllow: /\n").puntos_acceso == 25
    total = analizar_robots("User-agent: *\nDisallow: /\n")
    assert total.puntos_acceso == 0 and len(total.motores_sin_cita) == 3  # ChatGPT, Perplexity, Claude


def test_regla_propia_gana_al_comodin_en_el_desglose():
    txt = "User-agent: *\nDisallow: /\n\nUser-agent: PerplexityBot\nAllow: /\n"
    r = analizar_robots(txt)
    assert r.motores["Perplexity"].estado == "abierto"
    assert "Perplexity" not in r.motores_sin_cita


# --- puertas de CI -----------------------------------------------------------

def _resultado(total, sin_cita=()):
    return {"puntuacion": {"total": total}, "motores_que_no_pueden_citarte": list(sin_cita)}


def test_min_score_falla_el_build_por_debajo_del_umbral(monkeypatch):
    from geo_check import __main__ as m

    monkeypatch.setattr(m, "ejecutar", lambda *a, **k: _resultado(40))
    assert m.main(["https://ejemplo.com", "-q", "--min-score", "80"]) == 1


def test_min_score_pasa_cuando_se_alcanza_el_umbral(monkeypatch):
    from geo_check import __main__ as m

    monkeypatch.setattr(m, "ejecutar", lambda *a, **k: _resultado(80))
    assert m.main(["https://ejemplo.com", "-q", "--min-score", "80"]) == 0


def test_sin_puertas_siempre_sale_cero(monkeypatch):
    from geo_check import __main__ as m

    monkeypatch.setattr(m, "ejecutar", lambda *a, **k: _resultado(3, ["ChatGPT (OpenAI)"]))
    assert m.main(["https://ejemplo.com", "-q"]) == 0


def test_fail_if_blocked_solo_salta_si_un_motor_no_puede_citarte(monkeypatch):
    from geo_check import __main__ as m

    monkeypatch.setattr(m, "ejecutar", lambda *a, **k: _resultado(95, ["ChatGPT (OpenAI)"]))
    assert m.main(["https://ejemplo.com", "-q", "--fail-if-blocked"]) == 1

    monkeypatch.setattr(m, "ejecutar", lambda *a, **k: _resultado(95))
    assert m.main(["https://ejemplo.com", "-q", "--fail-if-blocked"]) == 0


def test_una_puntuacion_alta_no_salva_a_un_motor_bloqueado(monkeypatch):
    # El caso que motiva la puerta: 92/100 y aun asi ChatGPT no puede citarte.
    from geo_check import __main__ as m

    monkeypatch.setattr(m, "ejecutar", lambda *a, **k: _resultado(92, ["ChatGPT (OpenAI)"]))
    assert m.main(["https://ejemplo.com", "-q", "--min-score", "80", "--fail-if-blocked"]) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

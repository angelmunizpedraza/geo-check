# geo-check

[![CI](https://github.com/angelmunizpedraza/geo-check/actions/workflows/ci.yml/badge.svg)](https://github.com/angelmunizpedraza/geo-check/actions)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Comprueba si un sitio web está preparado para que lo lean, entiendan y citen los
buscadores generativos: ChatGPT, Perplexity, Claude, Google AI Overviews.

El SEO clásico responde a "¿me encuentra Google?". Esto responde a "cuando alguien
pregunta a una IA, ¿aparezco yo o mi competencia?". Son problemas distintos y casi
nadie audita el segundo.

## Instalación

```bash
pip install "geo-check @ git+https://github.com/angelmunizpedraza/geo-check"
```

O para trabajar sobre el código:

```bash
git clone https://github.com/angelmunizpedraza/geo-check
cd geo-check
pip install -e ".[dev]"
```

## Uso

```bash
geo-check https://ejemplo.com
```

Analizar también páginas concretas:

```bash
geo-check https://ejemplo.com https://ejemplo.com/cursos https://ejemplo.com/blog/guia
```

(`python -m geo_check` sigue funcionando igual.)

### Como puerta en CI

```bash
geo-check https://ejemplo.com --min-score 70 --fail-if-blocked --json geo-check.json
```

`--min-score N` devuelve 1 si la puntuación total baja de N. `--fail-if-blocked`
devuelve 1 si algún motor no puede citarte, por muy alta que sea la nota: una web
con 92/100 y `OAI-SearchBot` bloqueado sigue siendo invisible en ChatGPT, y eso no
debería pasar un despliegue.

### Como GitHub Action

```yaml
name: GEO check
on:
  push:
    branches: [main]
  schedule:
    - cron: "0 6 * * 1"

jobs:
  geo-check:
    runs-on: ubuntu-latest
    steps:
      - uses: angelmunizpedraza/geo-check@v1
        with:
          url: https://ejemplo.com
          min-score: "70"
          fail-if-blocked: "true"
```

| Entrada | Por defecto | Qué hace |
|---|---|---|
| `url` | — | Sitio a comprobar. Obligatorio. |
| `pages` | *(ninguna)* | URLs adicionales, separadas por espacios o saltos de línea. |
| `min-score` | `70` | Falla si la puntuación total baja de esto. Cadena vacía = solo informa. |
| `fail-if-blocked` | `true` | Falla si algún motor no puede citarte. |
| `json` | `geo-check.json` | Dónde escribir el informe JSON. |
| `python-version` | `3.12` | Python con el que se ejecuta. |
| `ref` | *(rama por defecto)* | Ref de git de geo-check a instalar. |

La CI de este repositorio ejecuta la propia action contra un sitio real en cada
push, así que está probada y no solo documentada.

## Qué comprueba

### 1. Acceso de los rastreadores de IA (25 puntos, desglosados por motor)

Lee `robots.txt` y evalúa el acceso **motor a motor**, no como una cifra única.
Bloquear `GPTBot` y bloquear `Google-Extended` son dos problemas distintos: si se
promedian, no sabes cuál te está costando la visibilidad.

Dentro de cada motor se distingue el papel de cada bot:

- **Bot de cita**: recupera la página en el momento de responder. Si lo bloqueas,
  ese motor no puede citarte, por muy bien que esté tu contenido.
- **Bot de entrenamiento**: alimenta el modelo. Bloquearlo tiene consecuencias a
  largo plazo, pero no te saca de la respuesta de hoy.

| Motor | Peso | Bots de cita | Bots de entrenamiento |
|---|---:|---|---|
| ChatGPT (OpenAI) | 8 | `OAI-SearchBot`, `ChatGPT-User` | `GPTBot` |
| Google AI Overviews / Gemini | 6 | — | `Google-Extended` |
| Perplexity | 5 | `PerplexityBot` | — |
| Claude (Anthropic) | 3 | `Claude-SearchBot` | `ClaudeBot`, `anthropic-ai` |
| Apple Intelligence | 1 | — | `Applebot-Extended` |
| Meta AI | 1 | — | `meta-externalagent` |
| Common Crawl | 1 | — | `CCBot` |

Los 25 puntos se reparten por ese peso, y dentro de cada motor un bot de cita vale
el doble que uno de entrenamiento. Consecuencia práctica: bloquear los tres bots de
OpenAI cuesta 8 puntos y bloquear tres motores menores cuesta 3, aunque en ambos
casos sean "tres bots bloqueados".

La salida marca aparte los motores que **directamente no pueden citarte** (todos
sus bots de recuperación en vivo bloqueados), que es el fallo caro y el que suele
pasar inadvertido.

Mucha gente bloqueó `GPTBot` en 2023 por miedo al entrenamiento y hoy no aparece en
ChatGPT Search. Con el desglose se ve la diferencia: si bloqueaste solo `GPTBot`,
ChatGPT todavía puede citarte a través de `OAI-SearchBot`; si bloqueaste también
ese, estás fuera.

El análisis respeta la lógica real de `robots.txt`: grupos con varios agentes,
excepciones a un bloqueo global (`User-agent: *` / `Disallow: /` más un
`Allow: /` para un bot concreto), comentarios y mayúsculas.

### 2. llms.txt (20 puntos)

Valida el archivo según [llmstxt.org](https://llmstxt.org): título H1, resumen en
blockquote, secciones H2 con listas de enlaces Markdown. Detecta:

- Ausencia del archivo o del título
- Resumen inexistente o demasiado corto
- Secciones vacías o enlaces mal formados
- Mayoría de enlaces sin descripción (la descripción es lo que el modelo usa para
  decidir qué abrir)

Incluye `generar_llms()` para crear uno válido desde datos estructurados.

### 3. Páginas (55 puntos)

Cada página se puntúa de 0 a 100 en tres bloques:

**¿Qué es esta página? (40)** — JSON-LD válido, con tipos que describan la entidad
(`Organization`, `Course`, `Article`, `FAQPage`, `Product`...) y con los campos
mínimos de cada tipo. Recorre `@graph` y objetos anidados.

**¿Se puede leer? (30)** — Palabras visibles sin JavaScript, ratio texto/HTML,
atributo `lang`. Si el contenido carga en cliente, el modelo ve una página vacía.

**¿Responde preguntas? (30)** — H1 presente, al menos dos H2, encabezados en forma
de pregunta o `FAQPage`. Los modelos citan fragmentos que responden a una pregunta
concreta, no páginas enteras.

## Ejemplo de salida

```
GEO CHECK · https://ejemplo.com
====================================================================

Puntuación global  █████████████░░░░░░░  67/100
  Acceso de bots IA    18/25
  llms.txt              0/20
  Páginas              49/55

── Acceso por motor (robots.txt) ──
  Motor                                  Estado     ¿Puede citarte?  Puntos
  ~ ChatGPT (OpenAI)                     parcial    sí               6.4/8
      ✗ GPTBot (entrenamiento)
  ✓ Google AI Overviews / Gemini         abierto    sí               6/6
  ✗ Perplexity                           bloqueado  NO               0/5
      ✗ PerplexityBot (cita)
  ✓ Claude (Anthropic)                   abierto    sí               3/3
  ✓ Apple Intelligence                   abierto    sí               1/1
  ✓ Meta AI                              abierto    sí               1/1
  ✓ Common Crawl                         abierto    sí               1/1

  ⚠ No pueden citarte: Perplexity.
    Sus bots de recuperación en vivo están bloqueados; el contenido no llega a la respuesta.

── llms.txt ──
  No existe. Es el primer archivo que un modelo busca para orientarse en el sitio.

── Páginas ──
  https://ejemplo.com/
  ██████████████░░ 89/100
    JSON-LD: Organization, WebSite
    1.240 palabras · ratio texto 23% · 6 H2 (2 en forma de pregunta)
    · AVISO: faltan og:title / og:description
```

## Uso como librería

```python
from geo_check import analizar_robots, validar_llms, analizar_pagina, generar_llms

acceso = analizar_robots(open("robots.txt").read())
print(acceso.puntos_acceso)      # 18  (de 25, ponderado por motor)
print(acceso.motores_sin_cita)   # ['Perplexity']  -> los que no pueden citarte

chatgpt = acceso.motores["ChatGPT (OpenAI)"]
print(chatgpt.estado, chatgpt.cita_bloqueada, chatgpt.puntos)   # parcial False 6.4

llms = validar_llms(open("llms.txt").read())
print(llms.valido, llms.problemas)

resultado = analizar_pagina("https://ejemplo.com/", html)
print(resultado.puntuacion, resultado.tipos_jsonld)
```

## Decisiones de diseño

**El parser de robots.txt está escrito a mano** en lugar de usar
`urllib.robotparser`. El de la biblioteca estándar responde "¿puede este bot ver
esta URL?", pero no expone la estructura de grupos, y para el informe necesito
saber *por qué* un bot está bloqueado: si por regla propia o heredada del comodín.

**La puntuación pondera más lo que está bajo tu control.** Que el sitio se pueda
leer y tenga datos estructurados depende de ti y se arregla en un día; por eso las
páginas pesan 55. El `llms.txt` es nuevo y muchos sitios buenos aún no lo tienen;
pesa 20 para no castigar de más.

**Los tipos JSON-LD se recorren recursivamente.** Casi todos los sitios serios usan
`@graph` con varias entidades anidadas; mirar solo el primer nivel se pierde la
mitad.

**El texto se cuenta después de eliminar `script`, `style` y `noscript`.** Una SPA
con 50 KB de JavaScript y tres frases visibles tiene ratio texto/HTML bajo y pocas
palabras: exactamente el problema que queremos detectar.

## Tests

```bash
pytest tests/ -v
```

29 tests. Los de `robots.txt` cubren los casos que aparecen en producción:
excepciones a bloqueos globales, varios agentes por grupo, comentarios en línea,
`Disallow` parcial que no debe contar como bloqueo, y el desglose por motor
(bloquear entrenamiento sin perder la cita, y al revés).

## Limitaciones

- No ejecuta JavaScript: en sitios renderizados en cliente verá lo mismo que ve
  un modelo sin navegador, que es justo lo que queremos medir.
- La puntuación es una heurística orientativa, no una métrica oficial de ningún
  buscador. Sirve para comparar antes y después, y entre competidores.
- No valida JSON-LD contra el vocabulario completo de schema.org, solo sintaxis,
  tipos y campos clave.

## Licencia

MIT

## Related tools

Part of a set of nine open-source tools I use on client work — all Python, MIT, deterministic, no API keys:

[render-gap](https://github.com/angelmunizpedraza/render-gap) · [llms-txt-generator](https://github.com/angelmunizpedraza/llms-txt-generator) · [citeable](https://github.com/angelmunizpedraza/citeable) · [serp-to-ai-diff](https://github.com/angelmunizpedraza/serp-to-ai-diff) · [ai-visibility-tracker](https://github.com/angelmunizpedraza/ai-visibility-tracker) · [linkjuice](https://github.com/angelmunizpedraza/linkjuice) · [seo-audit](https://github.com/angelmunizpedraza/seo-audit) · [ga4-report](https://github.com/angelmunizpedraza/ga4-report)

`geo-check` asks whether the AI crawlers are allowed in. `render-gap` asks whether anything was there when they arrived. `citeable` asks whether it was worth quoting.

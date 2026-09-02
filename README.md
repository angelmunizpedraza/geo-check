# geo-check

Comprueba si un sitio web está preparado para que lo lean, entiendan y citen los
buscadores generativos: ChatGPT, Perplexity, Claude, Google AI Overviews.

El SEO clásico responde a "¿me encuentra Google?". Esto responde a "cuando alguien
pregunta a una IA, ¿aparezco yo o mi competencia?". Son problemas distintos y casi
nadie audita el segundo.

## Instalación

```bash
git clone https://github.com/angelmunizpedraza/geo-check
cd geo-check
pip install -r requirements.txt
```

## Uso

```bash
python -m geo_check https://ejemplo.com
```

Analizar también páginas concretas:

```bash
python -m geo_check https://ejemplo.com https://ejemplo.com/cursos https://ejemplo.com/blog/guia
```

## Qué comprueba

### 1. Acceso de los rastreadores de IA (25 puntos)

Lee `robots.txt` y comprueba, bot a bot, si está bloqueado:

| Bot | Quién lo usa |
|---|---|
| `GPTBot`, `OAI-SearchBot`, `ChatGPT-User` | OpenAI: entrenamiento, búsqueda y navegación |
| `ClaudeBot` | Anthropic |
| `PerplexityBot` | Perplexity |
| `Google-Extended` | Google Gemini y AI Overviews |
| `Applebot-Extended` | Apple Intelligence |
| `CCBot` | Common Crawl, base de datos de muchos modelos |
| `Bytespider`, `meta-externalagent` | ByteDance, Meta |

Mucha gente bloqueó `GPTBot` en 2023 por miedo al entrenamiento y hoy no aparece en
ChatGPT Search. La herramienta te dice exactamente qué has bloqueado y a quién
pertenece.

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

Puntuación global  ████████████░░░░░░░░  61/100
  Acceso de bots IA    12/25
  llms.txt              0/20
  Páginas              49/55

── Rastreadores de IA (robots.txt) ──
  Bloqueados:
    ✗ GPTBot               OpenAI (entrenamiento)
    ✗ OAI-SearchBot        OpenAI (búsqueda en ChatGPT)
    ✗ ClaudeBot            Anthropic
  Permitidos: 8 de 11

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
print(acceso.bloqueados)   # {'GPTBot': 'OpenAI (entrenamiento)'}

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

22 tests. Los de `robots.txt` cubren los casos que aparecen en producción:
excepciones a bloqueos globales, varios agentes por grupo, comentarios en línea,
`Disallow` parcial que no debe contar como bloqueo.

## Limitaciones

- No ejecuta JavaScript: en sitios renderizados en cliente verá lo mismo que ve
  un modelo sin navegador, que es justo lo que queremos medir.
- La puntuación es una heurística orientativa, no una métrica oficial de ningún
  buscador. Sirve para comparar antes y después, y entre competidores.
- No valida JSON-LD contra el vocabulario completo de schema.org, solo sintaxis,
  tipos y campos clave.

## Licencia

MIT

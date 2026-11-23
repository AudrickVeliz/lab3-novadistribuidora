# Toma de pedidos por WhatsApp · NovaDistribuidora

Laboratorio 3 de Product Development (Universidad Galileo). Aplicación con modelos de lenguaje
que convierte los mensajes informales de WhatsApp de los tenderos en pedidos estructurados,
aplica las políticas de la empresa y envía a revisión humana lo que no puede resolver con certeza.

La versión entregada es el tag `entrega-lab3`. Las decisiones, con sus alternativas, están en
[DECISIONES.md](DECISIONES.md), y la evidencia de MLflow en [evidencia/](evidencia/).

## Levantar el producto

Requiere Docker con Compose, o Podman con `podman compose`. Los comandos son los mismos con
cualquiera de los dos (`docker compose ...` o `podman compose ...`).

1. **Código.** Clone la versión entregada:

   ```bash
   git clone --branch entrega-lab3 https://github.com/AudrickVeliz/lab3-novadistribuidora.git
   cd lab3-novadistribuidora
   ```

2. **Archivos publicados.** Descomprima el archivo publicado por el equipo docente **en la raíz
   del repositorio**, de modo que queden así (Git los ignora):

   ```
   datos/productos.parquet
   datos/sinonimos.parquet
   datos/precios_escala.parquet
   datos/clientes.parquet
   datos/historial_pedidos.parquet
   ejemplos/mensajes_dev.jsonl
   politicas.md
   catalogo_problemas.md
   ```

3. **Configuración.** Copie `.env.example` como `.env` y escriba su clave en `OPENROUTER_API_KEY`:

   ```bash
   cp .env.example .env
   ```

4. **Levantar** (la primera vez construye las imágenes, unos 3 minutos):

   ```bash
   docker compose up -d --wait
   ```

Queda disponible:

| Servicio | Dirección | Para qué |
|---|---|---|
| API | http://localhost:8000 | `POST /v1/pedidos/interpretar`, `GET /health` y la documentación en `/docs` |
| MLflow | http://localhost:5000 | Trazas de cada solicitud (experimento `toma-de-pedidos`) |

Ejemplo del Anexo:

```bash
curl -X POST http://localhost:8000/v1/pedidos/interpretar \
  -H "content-type: application/json" \
  -d '{"cliente_id": "C001", "fecha_hora": "2026-11-23T15:20",
       "mensajes": ["Buenas, mándeme 2 fardos de kola 600, una caja de aceite",
                    "y 48 latas de energía max"]}'
```

`docker compose down` detiene todo y conserva las trazas (volúmenes con nombre);
`docker compose down -v` también las borra.

> **Windows con Podman:** la redirección de puertos de WSL no responde en IPv6 (`::1`). Un
> cliente que prueba primero IPv6 con `localhost` espera unos 21 s antes de usar IPv4. Si pasa,
> use `http://127.0.0.1:8000`. Docker en Linux o macOS no tiene este problema (D-011).

## Configuración

`OPENROUTER_API_KEY` es la única variable obligatoria; las demás tienen el valor de
`.env.example`:

| Variable | Para qué | Por omisión |
|---|---|---|
| `OPENROUTER_API_KEY` | Clave de OpenRouter | (obligatoria) |
| `MODELO` | Modelo que interpreta los mensajes | `openai/gpt-6-luna` |
| `MODELO_ALTERNO` | Modelo que responde si el principal falla | `anthropic/claude-haiku-5.5` |
| `TIEMPO_LIMITE_MODELO_S` | Segundos máximos por llamada al modelo | `10` |
| `CARPETA_DATOS` | Carpeta de los parquet publicados | `datos` (en el compose, `/datos`) |
| `MLFLOW_TRACKING_URI` | Servidor de MLflow que recibe las trazas | `http://localhost:5000` (en el compose, `http://mlflow:5000`) |

`.env` no se sube a Git ni entra en las imágenes.

## Trazas en MLflow

Cada solicitud a `/v1/` deja una traza en el experimento `toma-de-pedidos`, con la entrada, la
respuesta, el código HTTP y, dentro, la llamada al modelo con sus tokens y su costo. Si MLflow
no está disponible, la API atiende igual y `GET /health` responde
`{"estado": "degradado", "motivo": "mlflow: no responde en ..."}` (D-010).

Para comprobar el producto levantado:

```bash
python tools/prueba_de_humo.py --pedido 200                  # /health, 422, 404, un pedido y su traza
docker compose stop mlflow
python tools/prueba_de_humo.py --pedido 200 --mlflow-detenido
docker compose start mlflow
```

## Reproducir la evaluación

La comparación de alternativas (D-012, D-014) corre los 84 casos publicados
(`ejemplos/mensajes_dev.jsonl`), los 40 propios de desarrollo (`evaluacion/casos_propios.jsonl`)
y los 15 de prueba (`evaluacion/casos_prueba.jsonl`), en el mismo formato, con cada modelo. Los
califica con código y registra un run por corrida en el experimento `evaluacion` de MLflow, con
la versión de las instrucciones (`VERSION_INSTRUCCIONES`) como etiqueta. Con el producto
levantado y el entorno de desarrollo (ver abajo):

```bash
python tools/evaluar.py                 # GPT-6 Luna y Haiku 5.5, 3 corridas cada uno
python tools/evaluar.py --resumir       # solo regenera la evidencia desde MLflow
```

El resultado queda en `evidencia/comparacion.md` y `evidencia/comparacion.csv`, y el detalle
de cada caso, con su traza, en http://localhost:5000 (experimento `evaluacion`).

Los casos propios y los de prueba se escriben en `evaluacion/fuente_casos_propios.json` y
`evaluacion/fuente_casos_prueba.json` con su interpretación correcta;
`python tools/generar_casos_propios.py` calcula la respuesta esperada con el motor de reglas y
regenera los `.jsonl`.

## Resultados

Configuración entregada: **GPT-6 Luna** como principal y **Claude Haiku 5.5** como alterno, con
las instrucciones v3 (D-014). Media de 3 corridas de Luna:

| Conjunto | Exactos | Latencia p50 | Costo por pedido |
|---|---|---|---|
| Prueba (15, escritos antes de ajustar las instrucciones) | 100 % | 3.4 s | US$0.00008 |
| Propios de desarrollo (40) | 100 % | 3.4 s | US$0.00008 |
| Publicados (84) | 98.8 % | 3.6 s | US$0.00011 |

- **Pedidos confirmados con error:** ninguno con Luna. Sus fallos son pendientes de "pasta"
  ambiguo, que van a revisión humana; Haiku confirmó 4 pedidos equivocados en 3 corridas.
- **Condiciones intactas:** en el 100 % de los 2,502 casos evaluados (18 corridas, incluidas las
  inyecciones): ningún mensaje cambió un precio ni un descuento.

La comparación completa (v1, v2 y v3 con los dos modelos) está en
[evidencia/comparacion.md](evidencia/comparacion.md), y el análisis en D-012 y D-014.

## Estructura del repositorio

| Ruta | Qué contiene |
|---|---|
| `src/novadistribuidora/` | `interprete.py` (cadena de LangChain y prompt), `interpretacion.py` (salida estructurada), `politicas.py` y `motor.py` (reglas de `politicas.md`), `confirmacion.py`, `servicio.py`, `api.py` (contrato del Anexo) y `trazas.py` (MLflow) |
| `tests/` | Pruebas con un intérprete falso, sin modelo ni servidores; cada política tiene una prueba que la nombra |
| `evaluacion/` | Casos propios y de prueba, en el formato de `mensajes_dev.jsonl`, con su interpretación correcta |
| `evidencia/` | Resultados de la comparación y capturas de MLflow |
| `tools/` | Evaluación, prueba de humo, generación de casos, revisión del flujo de Git y `verificar.py` |
| `compose.yaml`, `Containerfile*` | La API, MLflow y su base PostgreSQL |
| `DECISIONES.md` | Las decisiones técnicas y de producto, con sus alternativas |
| `CLAUDE.md` | El contexto y las reglas para el agente de programación |

## Desarrollo local

```bash
conda create -n lab3 python=3.12
conda activate lab3
pip install -e ".[dev]"
git config core.hooksPath .githooks   # una vez: revisa los commits y protege main
python tools/verificar.py             # lo mismo que corre CI
```

`tools/verificar.py --sin-pruebas` corre solo las revisiones rápidas: formato, lint,
workflows, finales de línea, rama y commits.

Para correr la API sin contenedores, con un MLflow local cuyos archivos quedan en el proyecto
(Git los ignora):

```bash
mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:///mlflow.db --artifacts-destination ./mlartifacts
uvicorn novadistribuidora.principal:crear_app_desde_entorno --factory --env-file .env --port 8000
```

## Integración continua

Cada PR y cada cambio en `main` pasa por el workflow *Verificar* (`.github/workflows/verificar.yml`):

| Trabajo | Qué revisa |
|---|---|
| `calidad` | Formato y lint con `ruff` (incluye reglas de seguridad), workflows con `actionlint`, finales de línea LF y vulnerabilidades de las dependencias con `pip-audit` |
| `pytest` | Pruebas con cobertura de ramas; falla por debajo del mínimo de `pyproject.toml` |
| `flujo` | Nombre de la rama y asuntos de los commits del PR |
| `contenedores` | Construye con Docker, escanea la imagen de la API con Trivy y corre la prueba de humo con MLflow arriba y detenido |

`main` exige los cuatro en verde. Además, GitHub analiza el código con CodeQL, bloquea los
secretos al hacer push y Dependabot propone actualizaciones semanales de dependencias, acciones
e imágenes.

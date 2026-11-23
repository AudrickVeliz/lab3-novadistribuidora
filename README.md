# Toma de pedidos por WhatsApp · NovaDistribuidora

Laboratorio 3 de Product Development (Universidad Galileo). Aplicación con modelos de lenguaje
que convierte los mensajes informales de WhatsApp de los tenderos en pedidos estructurados,
aplica las políticas de la empresa y envía a revisión humana lo que no puede resolver con certeza.

> En construcción: las instrucciones para levantar el producto con `docker compose up` y
> reproducir la evaluación se completan en los siguientes PR. Mientras tanto, el servicio se
> levanta localmente (ver "Levantar el servicio").

## Archivos publicados

Los archivos que publica el equipo docente no forman parte del repositorio. Descomprima el
archivo publicado **en la raíz del repositorio**, de modo que queden así:

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

## Configuración

Copie `.env.example` como `.env` y escriba su clave de OpenRouter en `OPENROUTER_API_KEY`. Es la
única variable obligatoria; las demás tienen el valor de `.env.example`:

| Variable | Para qué | Por omisión |
|---|---|---|
| `OPENROUTER_API_KEY` | Clave de OpenRouter | (obligatoria) |
| `MODELO` | Modelo que interpreta los mensajes | `anthropic/claude-haiku-5.5` |
| `MODELO_ALTERNO` | Modelo que responde si el principal falla | `openai/gpt-6-luna` |
| `TIEMPO_LIMITE_MODELO_S` | Segundos máximos por llamada al modelo | `10` |
| `CARPETA_DATOS` | Carpeta de los parquet publicados | `datos` |
| `MLFLOW_TRACKING_URI` | Servidor de MLflow que recibe las trazas | `http://localhost:5000` |

`.env` no se sube a Git ni entra en las imágenes.

## Levantar el servicio

```bash
uvicorn novadistribuidora.principal:crear_app_desde_entorno --factory --env-file .env --port 8000
```

La documentación interactiva queda en http://localhost:8000/docs. Ejemplo del Anexo:

```bash
curl -X POST http://localhost:8000/v1/pedidos/interpretar -H "content-type: application/json"   -d '{"cliente_id": "C001", "fecha_hora": "2026-11-23T15:20",
       "mensajes": ["Buenas, mándeme 2 fardos de kola 600, una caja de aceite",
                    "y 48 latas de energía max"]}'
```

## Trazas en MLflow

Cada solicitud a `/v1/` deja una traza en el experimento `toma-de-pedidos`, con la entrada, la
respuesta, el código HTTP y, dentro, la llamada al modelo con sus tokens. Para verlas en local,
levante MLflow antes que el servicio (los archivos quedan en el proyecto y Git los ignora):

```bash
mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:///mlflow.db --artifacts-destination ./mlartifacts
```

y abra http://localhost:5000. Si MLflow no está disponible, el servicio atiende igual y
`GET /health` responde `{"estado": "degradado", "motivo": "mlflow: no responde en ..."}` (D-010).

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

## Integración continua

Cada PR y cada cambio en `main` pasa por el workflow *Verificar* (`.github/workflows/verificar.yml`):

| Trabajo | Qué revisa |
|---|---|
| `calidad` | Formato y lint con `ruff` (incluye reglas de seguridad), workflows con `actionlint`, finales de línea LF y vulnerabilidades de las dependencias con `pip-audit` |
| `pytest` | Pruebas con cobertura de ramas; falla por debajo del mínimo de `pyproject.toml` |
| `flujo` | Nombre de la rama y asuntos de los commits del PR |

`main` exige los tres en verde. Además, GitHub analiza el código con CodeQL, bloquea los secretos al hacer push y Dependabot propone actualizaciones semanales.

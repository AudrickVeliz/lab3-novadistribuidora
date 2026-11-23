# Imagen de la API (D-011). Los datos y las credenciales no forman parte de la imagen:
# los datos llegan por volumen de solo lectura y la clave, por variables de entorno.
FROM docker.io/library/python:3.12.16-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MLFLOW_DISABLE_AGENT_HINT=1

WORKDIR /opt/novadistribuidora
COPY pyproject.toml ./
COPY src ./src
# Solo el paquete y sus dependencias de producción: sin el extra dev (pruebas, servidor MLflow).
RUN pip install .

RUN useradd --create-home --uid 1000 novadistribuidora
USER novadistribuidora

EXPOSE 8000
# El healthcheck vive en compose.yaml: el formato OCI de Podman descarta HEALTHCHECK.
CMD ["uvicorn", "novadistribuidora.principal:crear_app_desde_entorno", "--factory", "--host", "0.0.0.0", "--port", "8000"]

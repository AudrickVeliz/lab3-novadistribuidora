# Toma de pedidos por WhatsApp · NovaDistribuidora

Laboratorio 3 de Product Development (Universidad Galileo). Aplicación con modelos de lenguaje
que convierte los mensajes informales de WhatsApp de los tenderos en pedidos estructurados,
aplica las políticas de la empresa y envía a revisión humana lo que no puede resolver con certeza.

> En construcción: las instrucciones para levantar el producto con `docker compose up` y
> reproducir la evaluación se completan en los siguientes PR.

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

## Desarrollo local

```bash
conda create -n lab3 python=3.12
conda activate lab3
pip install -e ".[dev]"
pytest -q
```

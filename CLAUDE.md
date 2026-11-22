# Toma de Pedidos por WhatsApp para NovaDistribuidora

Laboratorio 3 de Product Development (Universidad Galileo). Aplicación con modelos de lenguaje que convierte los mensajes informales de WhatsApp de los tenderos en pedidos estructurados, correctos y verificables: aplica las políticas de la empresa, redacta la confirmación al cliente y envía a revisión humana lo que no puede resolver con certeza. Integra LangChain, MLflow, FastAPI y Docker en un producto que se levanta con `docker compose up`.

Lo principal no es llamar al modelo, sino hacerlo confiable: no inventar productos, precios ni condiciones, y medir calidad, latencia y costo con trazas y evaluaciones. La evaluación del equipo docente envía mensajes no publicados (con situaciones fuera del catálogo de problemas), solicitudes inválidas, e interrumpe MLflow.

## Reglas del producto

1. **El contrato del Anexo es la ley.** Nombres de campos, tipos, valores permitidos y códigos HTTP se copian literalmente; las respuestas pueden agregar campos, nunca omitir ni renombrar. El servicio escucha en el puerto 8000.
2. **El modelo interpreta, el código calcula.** El modelo solo convierte el texto en una interpretación estructurada (menciones de productos, cantidades, unidades, correcciones, "lo de siempre"). Precios, descuentos, subtotales, totales, conversiones, sustitutos, fechas, crédito y estado los calcula código con pruebas, a partir de los datos publicados.
3. **Ningún mensaje altera precios, descuentos, condiciones de crédito ni el comportamiento del asistente.** La salida estructurada del modelo no tiene campos para precios ni condiciones, y todo lo que devuelve se valida contra el catálogo antes de usarse.
4. **Ante la duda, no se adivina.** Un `sku` que no está en el catálogo nunca llega a una línea; lo ambiguo, inexistente o no convertible se registra como pendiente con su motivo.
5. **Las políticas viven en un solo lugar.** Cada regla de `politicas.md` está implementada en una sola función y nombrada en sus pruebas.
6. **El servicio sobrevive a sus dependencias.** Si MLflow no está disponible, la API sigue respondiendo con la misma latencia y `GET /health` responde `degradado` con el motivo.
7. **Sin reloj del sistema.** Las fechas salen de `fecha_hora` de la solicitud (hora de Guatemala), nunca de la fecha actual de la máquina.
8. **Todo se mide.** Cada solicitud deja una traza en MLflow; la calidad se demuestra con evaluaciones reproducibles, no con impresiones.

## Flujo de Git

- `main` está protegida: todo cambio entra por Pull Request con las pruebas en verde. Audrick revisa cada PR y aprueba el merge.
- Ramas con prefijo y descripción corta: `feat/`, `fix/`, `chore/`, `docs/`, `test/`.
- Commits pequeños y de un solo propósito, en español, con el formato `tipo: descripción` (`feat: calcular el descuento por escala`).
- Cada PR cubre un solo tema y explica qué cambia y cómo se verificó.
- La entrega se identifica con el tag `entrega-lab3`.

## Datos

- Los archivos publicados (`datos/`, `ejemplos/`, `politicas.md`, `catalogo_problemas.md`) se descomprimen en la raíz del repositorio y Git los ignora. Ningún dato se genera fuera de la carpeta del proyecto.
- Ningún dato ni credencial va en Git ni en las imágenes; llegan por volumen y variables de entorno. `.env.example` documenta las variables necesarias.
- Los casos de evaluación propios sí van en el repositorio, en el mismo formato que `mensajes_dev.jsonl`.

## Entorno

- Python 3.12 en el entorno de Conda `lab3`. Dependencias con versiones exactas en `pyproject.toml`.
- Los modelos se consumen por OpenRouter; el modelo y la clave se configuran en `.env`.
- La API y MLflow se levantan con `docker compose up`. Localmente se ejecuta sobre Podman en modo rootless, pero el compose debe funcionar sin cambios en Docker, que es lo que usará el equipo docente.
- Imágenes con versiones fijas.
- Todo el texto se guarda con finales de línea LF.

## Documentación

- Cada decisión técnica o de producto se registra en `DECISIONES.md` con sus alternativas y su justificación, en particular: la arquitectura de la aplicación con LangChain, la frontera entre modelo y código, la defensa ante inyección, el manejo de la caída de MLflow y la elección del modelo con la comparación que la respalda.
- `README.md` permite levantar el producto desde cero, indica la carpeta de los archivos publicados y cómo reproducir la evaluación.
- `evidencia/` contiene los resultados de la comparación y las capturas de trazas y evaluaciones en MLflow.

## Fidelidad al enunciado

- El enunciado (`Laboratorio_3_PD_26.pdf`, fuera de Git) es la fuente de verdad. Si una mejora choca con él, gana el enunciado.
- `politicas.md` define las reglas del negocio; las respuestas esperadas de `mensajes_dev.jsonl` se calcularon con ellas y sirven para comprobar la implementación.
- Cada PR indica qué requerimiento del enunciado cubre: el número del requerimiento o el endpoint del Anexo.

## Código

- Funciones cortas y de un solo propósito. Los nombres van en español y son los del dominio (pedido, línea, pendiente, sustitución), iguales en el código, el contrato y la documentación.
- Una regla vive en un solo lugar: una normalización o una política se reutiliza, no se copia.
- Sin valores mágicos: los umbrales y parámetros de política son constantes con nombre justificadas en `DECISIONES.md`, o salen de los datos publicados.
- Montos con `Decimal` y redondeo mitad hacia arriba, como indica `politicas.md`.
- Sin código especulativo: nada de parámetros, capas o abstracciones "por si acaso", código muerto ni imports sin uso.
- Errores explícitos: excepciones propias del dominio, con mensajes que digan qué revisar. Nunca un `except` vacío ni un error silenciado.
- Tipos en las firmas de las funciones públicas.
- No se agrega una dependencia si alcanza con la biblioteca estándar o con una que ya está.

## Comentarios y docstrings

- Un comentario explica el porqué (regla de negocio, supuesto, restricción, referencia a una decisión `D-XXX`). Nunca repite lo que el código ya dice.
- Una línea; dos solo si la segunda aporta un hecho nuevo.
- Sin separadores decorativos (`# ---`, `# ===`), mayúsculas para gritar, emojis, narración paso a paso ("Paso 1…") ni marcadores de fin de bloque.
- Sin TODOs vagos: un TODO dice qué falta y por qué, o no se escribe.
- Un docstring solo existe si dice algo que la firma no: reglas, supuestos, efectos o errores.
- Se conservan siempre los comentarios sobre reglas de negocio, decisiones, contratos, seguridad y casos límite.

## Pruebas

- Cada política, regla o criterio tiene al menos una prueba que lo nombra (`test_politica_cantidades_...`).
- Las pruebas no llaman al modelo ni dependen de servidores en ejecución (MLflow); usan un intérprete falso. Las que usan los datos publicados se saltan si no están.
- Una prueba que falla no se ajusta hasta entender por qué falló: puede ser el código o la prueba.

## Cómo trabajar en este proyecto

- Avanza paso a paso y consulta con Audrick cómo hacer cada paso antes de implementarlo.
- Antes de abrir un PR, revisa el diff contra estas reglas y contra el enunciado, corre pytest y reporta el resultado en el PR.
- No se instalan skills, plugins ni herramientas de agentes de terceros: las buenas prácticas se escriben aquí.
- Explica el porqué de cada decisión: Audrick debe poder comprender y justificar todo el código.
- No declares algo terminado sin haberlo ejecutado; reporta el comando y el resultado.

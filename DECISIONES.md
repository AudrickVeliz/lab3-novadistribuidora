# Decisiones técnicas y de producto

Cada decisión registra su contexto, las alternativas consideradas y su justificación.

## D-001: el modelo interpreta, el código calcula

**Fecha:** 2026-11-22

**Contexto:** el enunciado exige que los cálculos del negocio (precios, descuentos, totales, fechas y crédito) se hagan con código probado y que ningún mensaje pueda alterar precios, descuentos, condiciones de crédito ni el comportamiento del asistente. La evaluación envía mensajes no publicados que intentarán justamente eso.

**Decisión:** el modelo solo devuelve una `Interpretacion` estructurada: si el mensaje es un pedido, si pide "lo de siempre" y una lista ordenada de menciones. Cada mención trae el texto, los SKU candidatos, la cantidad, la unidad y la operación (agregar, corregir o quitar). Todo lo demás lo calcula `politicas.py`, una función pura por regla de `politicas.md`, a partir de los datos publicados:

- validar los SKU contra el catálogo;
- convertir unidades, sumar, corregir y quitar;
- expandir "lo de siempre";
- aplicar sustitutos, descuentos, crédito, fecha y estado.

**Alternativas:**

| Alternativa | A favor | En contra |
|---|---|---|
| Interpretación estructurada + reglas en código (elegida) | El modelo no tiene por dónde devolver un precio o una condición; cada regla se prueba sin el modelo | Hay que diseñar un esquema que cubra correcciones, exclusiones y "lo de siempre" |
| El modelo arma el pedido completo y el código lo valida | Menos código | Validar un total equivale a recalcularlo; el modelo puede "acomodar" el pedido a lo que pide el mensaje |
| Agente con herramientas que calculan | Flexible ante casos nuevos | El agente decide qué herramienta llamar y con qué datos: más latencia, costo y puntos de falla para un cálculo determinista |

**Justificación:** la separación cumple el requerimiento 1 por construcción: el esquema no tiene campos de precio, descuento, crédito ni fecha, y `extra="forbid"` rechaza cualquier campo adicional. Los SKU que propone el modelo se validan contra el catálogo antes de usarse, así que un SKU inventado no llega a una línea.

## D-002: el esquema de la interpretación se define con Pydantic

**Fecha:** 2026-11-22

**Contexto:** la interpretación es la frontera entre el modelo y el código. LangChain obtiene la salida estructurada a partir de un esquema, y FastAPI también usa Pydantic.

**Decisión:** `Interpretacion` y `Mencion` son modelos de Pydantic desde el motor de reglas. Las descripciones de los campos son parte de las instrucciones que verá el modelo.

**Alternativas:**

| Alternativa | En contra |
|---|---|
| `dataclasses` en el motor y un esquema Pydantic aparte para LangChain | Dos definiciones de lo mismo, con una conversión que puede divergir |
| JSON Schema escrito a mano | Sin validación de tipos ni rangos al recibir la respuesta del modelo |

**Justificación:** una sola definición sirve para pedirle la salida al modelo y para validarla al recibirla: una cantidad 0, una unidad desconocida o un campo extra se rechazan antes de llegar a las reglas.

## D-003: lectura de `politicas.md` verificada contra los ejemplos

**Fecha:** 2026-11-22

**Contexto:** varias reglas admiten más de una lectura. Las respuestas esperadas de `mensajes_dev.jsonl` se calcularon con las políticas, así que sirven para decidir cuál es la correcta.

**Decisión:** se adoptan las lecturas que reproducen los 84 casos sin discrepancias:

| Regla | Lectura adoptada | Caso que la confirma |
|---|---|---|
| §7 Fecha de entrega | La primera visita **estrictamente posterior** a la fecha de recepción; recibido a las 14:00 o después, cuenta desde el día siguiente | D001 |
| §5 Descuento | El mayor porcentaje de la categoría cuyo mínimo alcanza la cantidad de la línea | Casos con 10 o más unidades |
| §5 Redondeo | Mitad hacia arriba (`ROUND_HALF_UP`), con `Decimal` en todo el cálculo | Todos |
| §3 "Último pedido" | El pedido entregado con la fecha de entrega más reciente; si hubiera dos, el de mayor `pedido_id` | D017, D031 |
| §4 Sustituto | Ocupa el lugar del agotado; si su SKU ya estaba en el pedido, se suma a esa línea | D047 (A07 → A06) |
| §4 Pendiente de agotado | El texto es el nombre del catálogo y las opciones son el SKU agotado | D017, D027, D067 |
| §1 Opciones de un ambiguo | Incluyen productos agotados: el asesor decide | D064 ("cocas": B01, B02, B03) |
| §2 y §4 Orden | Se quita antes de revisar agotados: quitar un agotado no deja pendiente | D040 |
| Orden de las líneas | Primero las de "lo de siempre", en el orden del historial; después las nuevas, en orden de mención | D017, D044, D047 |

**Justificación:** la verificación se repite como prueba de regresión, así que un cambio que rompa una de estas lecturas se detecta en CI.

## D-004: casos que `politicas.md` no cubre

**Fecha:** 2026-11-22

**Contexto:** la evaluación incluye situaciones fuera del catálogo de problemas. Cada caso necesita una respuesta definida y probada, no una que dependa del modelo.

**Decisión:**

| Situación | Respuesta | Por qué |
|---|---|---|
| "Sin las naranjitas" cuando el catálogo tiene dos y solo una está en el pedido | Se quita la que está en el pedido | "Quitar" se refiere a lo pedido; no hay duda que resolver |
| Quitar algo que no está en el pedido | No hace nada | No hay línea que eliminar ni nada que revisar |
| Quitar algo ambiguo entre dos líneas del pedido | Pendiente `producto_ambiguo` con esas dos opciones | Ante la duda no se adivina (§1) |
| Corregir la cantidad de un producto no mencionado antes | Se agrega con esa cantidad | El cliente declara cuánto quiere de ese producto |
| Sustituto que también está agotado | Pendiente `agotado_sin_sustituto` | §4 exige un sustituto **disponible** |
| Opciones de `cantidad_no_convertible` | El SKU del producto | El producto es conocido; el asesor solo resuelve la cantidad |
| Varios motivos de revisión | Uno por tipo, en orden de aparición; `credito_excedido` al final | Orden estable para la respuesta y las pruebas |
| SKU del modelo con minúsculas o espacios | Se normalizan antes de validarlos contra el catálogo | Es un error de formato, no de interpretación |
| Pedido que termina sin líneas ni motivos (p. ej., "lo de siempre, pero sin nada de eso") | `fuera_de_alcance` | No hay nada que entregar ni que revisar; `requiere_revision` sin motivos violaría el contrato |

**Justificación:** cada respuesta sigue el principio de §1 ("ante la duda, no se adivina") y tiene su prueba en `tests/test_politicas_*.py`.

## D-005: los datos publicados se validan al cargar

**Fecha:** 2026-11-22

**Contexto:** el equipo docente coloca sus propios archivos publicados. Un archivo incompleto no debería producir pedidos con errores silenciosos.

**Decisión:** `cargar_datos` valida, antes de atender solicitudes:

- que existan los archivos y sus columnas;
- que los campos obligatorios no estén vacíos;
- que no se repitan SKU ni clientes;
- que cada sustituto exista en el catálogo;
- que `unidades_por_empaque` sea al menos 1;
- que los días de visita sean días de la semana.

Si algo falla, lanza `DatosInvalidos` con un mensaje que dice qué revisar. Los montos se convierten a `Decimal` desde su representación de texto.

**Alternativas:**

| Alternativa | En contra |
|---|---|
| Validar en cada solicitud | El error aparece a mitad de un pedido y como error 500 |
| No validar | Un sustituto inexistente o un día mal escrito darían pedidos incorrectos sin aviso |

**Justificación:** fallar al arrancar con un mensaje claro es más fácil de diagnosticar que un pedido mal calculado.

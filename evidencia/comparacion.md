# Comparación de alternativas del intérprete

Generado por `tools/evaluar.py` (D-012). Media ± desviación estándar entre corridas.

| Alternativa | Conjunto | Corridas | Exactos | Estado | Líneas | Pendientes | Condiciones intactas | Errores | Latencia p50 (s) | Latencia p95 (s) | Costo por pedido (US$) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| haiku | propios (40) | 3 | 97.5% ± 0.0% | 97.5% ± 0.0% | 97.5% ± 0.0% | 98.3% ± 1.4% | 100% ± 0% | 0.0 ± 0.0 | 1.45 ± 0.11 | 2.84 ± 0.29 | 0.00045 ± 0.00001 |
| haiku | publicados (84) | 3 | 99.6% ± 0.7% | 100.0% ± 0.0% | 99.6% ± 0.7% | 99.6% ± 0.7% | 100% ± 0% | 0.0 ± 0.0 | 1.62 ± 0.07 | 3.57 ± 0.24 | 0.00049 ± 0.00000 |
| luna | propios (40) | 3 | 96.7% ± 1.4% | 96.7% ± 1.4% | 96.7% ± 1.4% | 99.2% ± 1.4% | 100% ± 0% | 0.0 ± 0.0 | 2.65 ± 0.08 | 4.74 ± 1.17 | 0.00009 ± 0.00001 |
| luna | publicados (84) | 3 | 98.8% ± 1.2% | 100.0% ± 0.0% | 99.6% ± 0.7% | 98.8% ± 1.2% | 100% ± 0% | 0.0 ± 0.0 | 2.75 ± 0.03 | 3.85 ± 0.16 | 0.00010 ± 0.00000 |

## Casos fallidos

| Alternativa | Caso | Tipo | Corridas fallidas |
|---|---|---|---|
| haiku | P017 | unidades | 2 de 3 |
| haiku | P022 | unidades | 1 de 3 |
| haiku | D048 | no_existe | 1 de 3 |
| luna | P017 | unidades | 1 de 3 |
| luna | P022 | unidades | 3 de 3 |
| luna | D008 | ambiguo | 1 de 3 |
| luna | D014 | ambiguo | 1 de 3 |
| luna | D031 | habitual | 1 de 3 |

# Cómo se informa el avance

En cada cierre de trabajo informar el porcentaje de entregables terminados y el porcentaje aún no cerrado, con sus denominadores. Informar aparte la cobertura de implementación parcial y los criterios concretos del bloque entregado.

La métrica global cuenta **100 componentes C + 100 disciplinas D**. No representa horas trabajadas, líneas de código, cantidad de pruebas ni una estimación ponderada del esfuerzo. Una disciplina especificada o vinculada a un módulo no se cuenta como terminada.

El estado actual es:

| Medida | Conteo | Porcentaje |
|---|---:|---:|
| Componentes completamente aceptados | 0/100 | 0% |
| Componentes con implementación parcial | 22/100 | 22% |
| Disciplinas completamente aceptadas | 0/100 | 0% |
| Disciplinas especificadas | 100/100 | 100% |
| Total de entregables cerrados | 0/200 | 0% |
| Entregables todavía no cerrados | 200/200 | 100% |

Los 22 componentes parciales contienen código real probado dentro de un alcance acotado. Todavía no satisfacen todo el alcance y dependencias de sus filas; sus mejoras sucesivas no los convierten automáticamente en completos.

`tools/check_operational_catalog.py` calcula estos valores a partir del catálogo y `docs/completion_register.json`. Para registrar un cierre, se exige una aceptación de alcance completo que corresponda al requisito del catálogo, un informe fijado por hash y referencias a comprobaciones también fijadas por hash. En componentes, su estado debe concordar con el registro y el contador total. Los registros son decisiones de aceptación documentadas, no una certificación independiente emitida por este script.

El registro de cierres actual está vacío. Los datos de aceptación sintéticos usados por las pruebas del contador permanecen únicamente en directorios temporales y no entran en este registro.

El bloque v0.20 reúne cinco criterios de reutilización segura del registro, contraste con 0.19 y conservación de verificación por expediente (`REGISTRY_CACHE_ACCEPTANCE.json`). Los cinco pasaron: **100% del bloque acotado**. La prueba prolongada se registra por separado; no cierra objetivos globales.

Consultar el resultado reproducible con:

```bash
python3 -B tools/check_operational_catalog.py
```

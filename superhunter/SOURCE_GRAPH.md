# Inventario real de imports Python — alcance acotado

Este módulo analiza el código del propio paquete SUPERHUNTER mediante `ast`.
No importa los archivos analizados, no ejecuta sus instrucciones, no abre una
conexión de red y no acepta un objetivo externo. Es un grafo sintáctico de
imports, **no** SlithIR, un grafo de llamadas, un detector de vulnerabilidades,
un análisis de CVEs ni una prueba de alcanzabilidad en ejecución.

## Ejecución

```bash
python3 -m superhunter audit-source-graph --out /ruta/privada/imports-nuevos
python3 -m superhunter verify-source-graph --bundle /ruta/privada/imports-nuevos
```

La carpeta debe ser nueva y estar fuera del checkout. `python3 -m
superhunter.source_graph ...` admite las mismas opciones. El segundo comando
reconstruye el grafo desde los bytes de fuentes capturados, sin necesitar las
carpetas originales. No autentica a un productor remoto. Un paquete reescrito
completamente junto con sus fuentes y hashes puede seguir siendo consistente.

Códigos de salida: 0 si terminó el inventario sin observaciones de revisión;
1 si terminó y hay imports sin resolver, carga dinámica o conexiones no
respaldadas por el registro declarado; 2 si hubo error. **Ninguno significa
que se haya demostrado seguridad o descubierto una vulnerabilidad.**

## Qué calcula

Resuelve imports absolutos y relativos cuando existe el archivo correspondiente
en la captura. Distingue sitios a nivel de módulo, condicionales y diferidos en
funciones. Los argumentos predeterminados y decoradores se consideran en su
contexto exterior. No evalúa condiciones; un import escrito dentro de `if False`
permanece como conexión posible y condicional.

Deriva grupos de ciclos, referencias desde los módulos de entrada y dependencias
entre componentes. Extrae la asignación literal `COMPONENTS` de `quality.py`
sin ejecutar ese archivo. Distingue dependencias declaradas DIRECT, TRANSITIVE
y ABSENT. Una dependencia transitiva no se etiqueta como ausente; un registro
QA no es una prueba de las llamadas realizadas en producción.

Registra los imports no resueltos y ciertos sitios explícitos de carga dinámica,
sin inventar sus destinos. No usa el nombre de una biblioteca como prueba de
que esté instalada, tenga una versión determinada o sea vulnerable.

Los originales quedan privados e intactos. El paquete tiene un manifiesto de
fuentes, un grafo JSON, un reporte Markdown y un marcador COMPLETE.json. Se
comprueban hashes, tipos, conjuntos de archivos, rutas y límites. La verificación
recalcula el grafo y el reporte: cambiar un vínculo o una declaración de seguridad
no pasa solo por regenerar el manifiesto externo.

## Conexión con la plataforma

En la entrega acumulativa el componente está registrado en QA y su CLI. El
recorrido `review-platform` incorpora `source-imports.json` y SOURCE_IMPORTS.md;
el reporte portátil calcula el mismo resumen desde el código actual. Las pruebas
del componente forman parte de la suite conjunta, con controles obligatorios.

La publicación focalizada en GitHub, cuando se indique, puede contener solo el
módulo y sus pruebas sobre la base remota. Esa variante no reemplaza la entrega
acumulativa de permisos, privacidad, regresiones e iniciativas: comprobar siempre
el manifiesto de publicación antes de sustituir una copia local.

## Límites que permanecen explícitos

Se analizan hasta 256 archivos .py de runtime y 8 MB agregados, no los tests.
No se resuelven todos los alias de cargadores dinámicos, hooks de importación,
monkeypatching, importaciones implícitas de __init__, atributos reexportados o
módulos creados mediante exec. Las rutas de fuentes nativas importadas representan
su estructura de archivos; el cargador puede asignarles otros nombres en memoria.

No alcanzar un módulo por imports sintácticos NO demuestra código muerto.
Un ciclo NO prueba un fallo. Un módulo faltante en una función no utilizada NO
prueba una vulnerabilidad. La salida conserva incertidumbre y solicita revisión.

La revisión ejecutada sobre la base acumulativa detectó la referencia diferida
a `native_sources/diablo/ratelimit.py`, ausente en el subconjunto importado. Ese
método no forma parte del recorrido usado por el laboratorio. Se conserva la
fuente nativa fijada y se reporta el límite; no se altera para maquillar el grafo.
La carga fijada mediante exec de `native_runtime.py` también queda identificada
como un punto que el análisis estático no resuelve automáticamente.

Avance parcial del requisito 30 (inventario de dependencias). No completa
alcanzabilidad de funciones vulnerables, análisis Solidity ni el Hunter. Los
27 requisitos, 50 capacidades y 25 iniciativas permanecen separados.

Referencias de interfaz consultadas el 4 de noviembre de 2026:
https://docs.python.org/3/library/ast.html
https://docs.python.org/3/reference/import.html
Implementación original, sin fuentes de herramientas de terceros copiadas.

## Reutilización determinista para reportes

Los reportes repetidos del paquete reutilizan como máximo cuatro resultados
calculados a partir de los mismos bytes exactos de fuentes. La caché conserva
bytes JSON inmutables y devuelve una copia nueva; un cambio de fuente invalida
la entrada. `verify-source-graph` no usa esa caché y vuelve a analizar las fuentes
del paquete. Las pruebas cubren invalidación, no mutación compartida y verificación
sin caché. No es una segunda implementación ni un productor independiente.

# Fuentes y caché de los workers QA

Cada uno de los ocho procesos QA arranca con `-I -B -X pycache_prefix=RUTA`,
donde RUTA es un directorio nuevo, privado y exclusivo del worker dentro del
área temporal de esa ejecución. Se elimina también cuando el worker falla.
`-B` impide escribir bytecode, pero por sí solo permite leer una caché existente.
El prefijo nuevo evita que el worker use cachés anteriores junto a las fuentes.

Dos controles propios compilan un módulo con `VALUE = 2`, conservan ese bytecode
y cambian el fuente a `VALUE = 1`: uno conserva tamaño/mtime y otro utiliza una
caché de hash sin comprobación. El arranque anterior devuelve 2; las opciones
reales del nuevo lanzador devuelven 1. Los bytes del fuente y de la caché de
control se conservan; no se modifica ninguna captura histórica para aprobar.
El control anterior de dos motores EVM crea ahora su caché de prueba explícita
en el directorio estándar, independientemente del prefijo del intérprete padre.

El QA conserva las ocho particiones, todas las pruebas y los límites de
180 s de pared, 90 s CPU, 2 GiB de memoria y 20 MiB por archivo. No se añade una
ruta de pruebas arbitraria ni un destino externo. La prueba de fallo de #61
continúa conservando recibos sin producir PASS.

Alcance: caché de importaciones en los workers Python lanzados por `check`.
No autentica al productor, no fija todos los bytes del intérprete o bibliotecas
nativas, no elimina carreras causadas por un proceso local hostil y no certifica
un sandbox. El proceso padre debe iniciarse desde un entorno de confianza; este
cambio no corrige módulos que el padre hubiera importado antes de ejecutar QA.

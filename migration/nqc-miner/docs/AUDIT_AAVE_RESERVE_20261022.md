# Auditoría: índices de reserva y saldos escalados Aave

Entrega y reverificación: 23 de octubre de 2026. El nombre del directorio
conserva la fecha de preparación. Avance global: **43/100**.

`project-aave-reserve` reproduce el recorrido de caché y actualización de una
reserva de la fuente Aave revisión 11 retenida: interés lineal de liquidez,
polinomio de interés variable, acumulación de tesorería y conversión de saldos
escalados a colateral y deuda. Conserva el orden de operaciones, el redondeo y
los bytes de reversión, incluidos los argumentos de SafeCast. Las entradas
ausentes, ambiguas o fuera de su ancho entero se rechazan.

La referencia Solidity importa las funciones originales sin modificar sus
fuentes. La lectura de deuda total y el almacenamiento del harness son
sintéticos. REVM ejecuta sus funciones con almacenamiento explícito y Cancun;
esto no reproduce el fork ni el estado de una transacción histórica.

## Verificación

- 182 pruebas Rust y 269 Python aprobadas: **451** en total, sin fallos ni
  omitidas. Los casos diferenciales están incluidos en esas pruebas.
- 1106 entradas se ejecutan con una actualización y con dos actualizaciones
  en el mismo bloque: **2212 ejecuciones diferenciales**. Se comparan nueve
  palabras ABI o todos los bytes de reversión. Por cada modalidad hay 1091
  éxitos, cinco reversiones vacías, siete pánicos y tres errores SafeCast.
  Otras pruebas añaden tres ejecuciones de referencia dirigidas.
- Clippy con advertencias como errores, formato, alcance, aislamiento e
  identidad del binario aprobados. La identidad de compilación corresponde a
  `085101caafa6927725213c22de552c72ef00b0da`, con `source_dirty=false`.
- Se conserva el resultado del aislamiento: 531 archivos originales,
  106 workflows deshabilitados y cero activos. El cambio está limitado a
  `migration/nqc-miner/`.
- Una nueva compilación con solc 0.8.27 de hash fijado produjo exactamente las
  mismas entradas, salidas y fixture que el respaldo. Runtime: 2530 bytes,
  SHA-256 `b1113b61b0464b7c959e74a6a8f6e942ae1b71f0b7d7603fd0fb8704e5081c05`.

## Recuperación y trazabilidad

El entorno temporal se reinició antes de publicar la entrega. El código se
recuperó del bundle previamente subido a GitHub, conservando el commit exacto
`085101c`. El bundle requiere `ac41b44`, recuperable desde el bundle de importes
ya publicado. No se reconstruyeron ni inventaron los logs perdidos: `offline/`
contiene una ejecución completa nueva, y `targeted-recovery.txt` la repetición
dirigida. `targeted-initial.txt` conserva el log original que sí estaba incluido
en el respaldo. La primera batería recuperada (`offline-initial/`) registró 58
errores Python por commits antiguos ausentes en el clon superficial; se
restauró el historial original y se repitió la batería completa. Ese fallo
queda conservado, sin cambiar fuentes ni debilitar las comprobaciones.

La caché recuperada no contenía todas las dependencias: el primer intento
offline se detuvo por `alloy-sol-types` ausente. Se descargaron las dependencias
con el lock existente, sin cambios en Cargo.lock; la batería retenida después
se ejecutó offline. La recompilación Solidity usa el compilador cuyo hash
verifica el constructor. Esto no se presenta como un entorno hermético.

`verification.json` fija los hashes de las fuentes auditadas, documentación y
evidencia. Los logs registran comandos, tiempos y resultados de esta ejecución.

## Límite de la conclusión

Los balances y totales suministrados siguen sin autenticación histórica. No
se compone todavía una certificación completa con condiciones e importes. Se
mantienen abiertas salud agregada/eMode, consumo de colateral escalado, tope
final de comisión, quema de deuda, déficit, liquidez, transferencias, cambios de
tasas y estado justo antes de la transacción. No hay nuevos eventos históricos,
ejecución completa de liquidaciones ni certificación económica.

Observer no cambia. No se habilitan workflows, despliegue, firma ni gasto, y
no se asignan puntos adicionales por este núcleo parcial.

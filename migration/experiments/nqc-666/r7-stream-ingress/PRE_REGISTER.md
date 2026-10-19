# R7 — diseño y medición antes de ejecutar el benchmark

Base inmutable R6: e5842cc676c93c99f08025ae22537fcc8a041fca.
R5 continúa siendo el verificador predeterminado. No se vuelve a ensayar la
optimización hexadecimal/objeto rechazada en R6.

Hipótesis funcional: una captura fragmentada puede conservar exactamente los
resultados de R5 cuando es válida y revocar cualquier resultado anterior desde
el inicio de una actualización. Tamaño acumulado <=2 MiB, <=1024 fragmentos,
offset exacto, bytes inmutables no vacíos, un solo propietario, ningún hilo nuevo.
Plazo de captura <=50 ms desde la inicialización del buffer, sin reiniciarlo al
recibir fragmentos. Revocación inicial/validación de política preceden ese reloj;
la ventana externa del benchmark sí las incluye. La caducidad monotónica se fija
al comienzo de la captura. Un plazo se comprueba al llamar a la API; no hay
preempción ni temporizador en segundo plano. El estado anterior no se usa mientras
la captura está pendiente. La memoria pendiente está acotada aunque cese el tráfico.

Condiciones de aceptación funcional: pruebas positivas equivalentes a R5;
rechazo de captura inválida, incompleta, reordenada, atrasada, sobredimensionada,
duplicada, de otra cadena/bloque, con recibo ajeno o tras interrupción/reentrada;
sin emisión de hechos parciales ni admisión comercial. Sin cambios R0–R6.

Medición: 16 fixtures sintéticos R3/R6 originales, 13 precios condicionales,
orden reproducible. Tres perfiles: un fragmento, 4096 bytes, 257 bytes. No son
distribuciones observadas de red. 3 repeticiones × 2048 parejas × 3 perfiles ×
2 variantes = 36.864 ventanas. Semillas 666701+rep*3+perfil, se alterna el orden.

Comparador R6: reset + ensamblaje por join + SHA256 + ingest R5 + escenario Rust
+ autorización cerrada. R7: begin/feed + SHA256/finish R5 + escenario Rust +
autorización cerrada. Los fragmentos ya están preparados en memoria antes de
ambas ventanas. Se incluye el ensamblaje; se excluyen lectura de archivo, red,
HTTP, generación de fragmentos, construcción del motor, oráculo/IRM/EVM y builder.
El resultado completo se observa, hashea y compara fuera de la ventana.

Cuatro fases medidas por igual: assembly, verification, scenario, authorization;
total = suma exacta de las fases. El total externo incluye invocaciones Python,
instrumentación, validación y todo el recorrido local. En fallos se conserva
el tiempo hasta rechazo y se rellenan las fases posteriores con cero; no se
confunde con un recorrido exitoso. No se eliminan descartes ni máximos.

Se publican mediana, p95, p99, p99.9, máximo y mínimo por perfil/variante/fase y
por repetición, raw binario u64 LE, estados, orden, calibración, hashes,
CPU/afinidad/frecuencia disponible, compilador/dependencias y condiciones.
GC habilitado, CPU permitida menor, CLOCK_MONOTONIC_RAW, sin restar overhead.

Esto mide el coste de **defensas adicionales**, no una optimización de semántica
equivalente. No autoriza cambiar R5 ni prometer menos latencia. No se promueve
R7 a uso operativo: falta testigo auténtico, corpus representativo y validación
de red/oráculo/ejecución. Si aparece un descarte, se conserva y se documenta.
No se ejecuta ningún experimento de 5 ns porque este componente no corresponde
a ese alcance. La evidencia negativa auténtica se usa para rechazo, nunca para
construir pruebas sintéticas y llamarlas estado real.

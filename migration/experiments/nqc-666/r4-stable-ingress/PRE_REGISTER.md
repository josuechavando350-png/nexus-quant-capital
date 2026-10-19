# R4 — incorporación local y estabilidad comprobable

R3 queda inmutable en b68361d28f2ee971f941c0eb5440135c9df97b83. Un único intento
de lectura pública de encabezado devolvió 403; se detuvo, sin reintento ni ruta
alternativa. No existe un testigo real completo incorporado. El importador offline
debe aceptar evidencia relativa al pin configurado o rechazarla sin hechos parciales.

Problemas a corregir: tickets R3 indistinguibles entre instancias con misma época/bloque;
espera de IPC sin plazo ante un worker silencioso; caducidad que dependía exclusivamente
del reloj proporcionado por el llamador. Se reproducen con procesos de prueba acotados.

Cambios: Rust R1 en una biblioteca local con ABI por valor, sin punteros de usuario ni
`unsafe` en el wrapper Rust; tickets por identidad de objeto/instancia/época/posición;
expiración monotónica y descarte de resultados tardíos. Se conserva el verificador R3.
No se retira ninguna comprobación financiera existente ni se habilita una operación.

Presupuestos de aceptación propuestos antes de medir: 50 ms por verificación, 5 ms por
escenario preparado. **Son plazos para descartar resultados, no límites de ejecución.**
No interrumpen al host o al verificador. Se registrará cada rechazo junto con su latencia,
sin hacer desaparecer los picos para mostrar un resultado favorable.

Matriz, tres repeticiones en orden intercalado con semilla 666404:

| Modo | Variantes | Muestras por corrida | Total |
|---|---|---:|---:|
| Matemática preparada | R1 IPC, R1 ABI nativo | 16.384 | 98.304 |
| Escenario sobre snapshot ya verificado | R3+IPC, R3+nativo, R4+nativo | 8.192 | 73.728 |
| Ingreso con pruebas + escenario | R3+IPC, R3+nativo, R4+nativo | 4.096 | 36.864 |

Total: **208.896 ventanas individuales**, 24 corridas. Corpus de 16 pruebas sintéticas
R3 sin alterar. Precios supuestos varían; el resultado debe coincidir exactamente con
R1/R3 para cada intento aceptado. Los rechazos nuevos solo se admiten por plazos/expiración
y se contabilizan por separado. No se elimina ninguna muestra de la distribución.
El modo intermedio R3+nativo separa el coste de integración del de los nuevos controles.

Reloj CLOCK_MONOTONIC_RAW para medir; reloj monotónico estándar para caducidad del gateway.
64 llamadas de calentamiento por corrida. Afinidad a una CPU permitida, sin modificar
frecuencia, IRQ, NUMA o prioridades del host. GC Python activo. Se conservan n, mediana,
p95, p99, p99.9, máximo, muestras, estados y controles de reloj, sin sustracciones.

La construcción/carga y comprobación de hash de la biblioteca, arranque del worker,
buffers de evidencia y política están fuera de las ventanas. En el modo de escenario
preparado, la verificación del snapshot también está fuera. En ingreso se incluye
reset, JSON, todas las pruebas R3, ticket, escenario y denegación de autorización.
Serialización diagnóstica/checksum se realiza fuera de cada ventana. Los resultados
se consumen y comparan con el esperado; no hay eliminación de trabajo por compilación.

Se publican regresiones además de mejoras. Una menor mediana no demuestra un máximo
operacional estable. No se atribuirá una diferencia entre corridas al IPC o un guardián
restando medianas; se comparan caminos equivalentes completos. La integración nativa
comparte proceso con Python: elimina el bloqueo de pipe, pero no aísla un defecto nativo.
Se exige contraste de ABI, límites, errores y equivalencia antes de aceptarla en investigación.

No se mide red, consenso, oracle/IRM ejecutados, simulación Morpho completa, builder,
financiación, admisión comercial ni inclusión. El próximo testigo real debe tener su
propia procedencia y política de confianza; un fixture no satisface ese requisito.

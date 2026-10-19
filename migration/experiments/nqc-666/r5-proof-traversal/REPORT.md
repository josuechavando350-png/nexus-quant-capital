# NQC 666 R5 — mejora incorporada; estabilización integral pendiente

El verificador R5 elimina el segundo recorrido y reutiliza nodos ya validados. Está conectado al gateway con las defensas R4 y al importador offline. **La mejora supera el criterio local registrado; el bot completo todavía no está certificado como estabilizado.**

Base inmutable: `488ba082a7e5f779c2a675b4089974615da88a92`. Solo se añade esta carpeta. La biblioteca Rust recompilada conserva el SHA256 `1cc575699de5a9395dc95b6cc17fbabae0c355459948ba91ef11d204ef0388f4`.

## Medición reproducible

49.152 ventanas individuales: 3 repeticiones × 4.096 pares × 2 modos × 2 variantes. Mismos 16 paquetes sintéticos de pruebas MPT R3; 208 combinaciones de paquete/precio para el ingreso. Orden de variantes alternado y entradas barajadas. Todos los intentos y picos se incluyen. No se restó el reloj.

CPU AMD EPYC 9V74 en KVM, afinidad CPU 0, GC habilitado, Python 3.12.14, Rust 1.90.0/LLVM 20.1.8; O3 y fat LTO sin cambios. Frecuencia real del host, carga e interrupciones no controladas. UTC: 2026-10-19T01:01:21Z a 2026-10-19T01:03:04Z.

Valores en **nanosegundos**, medidos por llamada completa:

| Etapa | Variante | Mediana | p95 | p99 | p99.9 | Máximo |
|---|---|---:|---:|---:|---:|---:|
| Verificación completa del paquete | R4 | 2,562,343 | 3,946,945 | 5,064,588 | 7,412,342 | 10,558,325 |
| Verificación completa del paquete | R5 | 1,346,454 | 2,162,679 | 2,828,811 | 5,151,307 | 7,356,830 |
| Ingreso local + escenario + puerta cerrada | R4 | 2,632,929 | 3,923,550 | 5,039,110 | 8,809,592 | 23,604,733 |
| Ingreso local + escenario + puerta cerrada | R5 | 1,398,712 | 2,180,225 | 2,950,842 | 5,241,882 | 10,295,554 |

Cambios frente a R4, sobre todos los intentos:

| Etapa | Mediana | p99 | p99.9 | Máximo |
|---|---:|---:|---:|---:|
| proof | -47.45% | -44.15% | -30.50% | -30.32% |
| full_ingress | -46.88% | -41.44% | -40.50% | -56.38% |

La mediana mejoró >10% en las seis comparaciones por repetición/modo. p99, p99.9 y máximo agregados cumplieron el límite previo <=105% del baseline en ambos modos. Se selecciona R5 como camino **experimental local**, sin cambiar R4 ni eliminar su evidencia anterior.

Hubo **un descarte R4** por exceder el plazo del escenario (rep1, pareja 961, ventana total 16.379.228 ns), incluido en la distribución. R5 tuvo cero descartes en esta muestra. Las salidas de cada pareja aceptada por ambos fueron iguales; la pareja descartada no se presenta como dos salidas iguales. Sus hashes agregados difieren en esa ronda por el descarte. Ninguna autorización comercial fue concedida.

El reloj vacío tuvo mediana 210–211 ns por ronda; máximo de calibración 252.646 ns. Esto muestra que el instrumento/entorno también presenta pausas, pero no permite atribuir cada pico del programa al host. Los tiempos brutos quedan intactos. Un máximo observado no es una cota futura.

## Corrección y límites preservados

- 75 pruebas Python finales aprobadas: 7 pruebas nuevas, 18 pruebas R3 ejecutadas para cada verificador y 16 R4 para cada gateway. Las pruebas heredadas de gateway R3 y del CLI R4 siguen probando ese componente histórico; no se atribuyen a R5. La prueba nueva de CLI ejecuta el importador R5 y verifica rechazo de encabezado real sin testigo.
- Diferencial de 2.472 variantes de pruebas de árboles generados, evaluadas en cuatro combinaciones (R4/R5 y caché compartida/individual). Incluye claves presentes/ausentes, prefijos, inline, orden cambiado, nodos duplicados y omisiones. Además, la suite R3 conserva sus 256 mutaciones de bytes y comprobaciones semánticas.
- 2 pruebas Rust R4 + 5 Rust R1 + 9 de aislamiento aprobadas. El verificador de aislamiento conserva 0 workflows activos y 106 deshabilitados. No se repitieron los conjuntos históricos Solidity/EVM y financieros no afectados; véase PROVENANCE.
- Cuerpos verify/_verify idénticos a R3; clases Ticket/StableGateway equivalentes por AST a R4. Caducidad monotónica, identidad, revocación, rechazo de cancelación/reentrada y resultados tardíos siguen cubiertos.
- Ninguna caché cruza paquetes. Cada prueba tiene su mapa propio; la caché no puede suplir un nodo que falta en esa prueba. Los hermanos inline no recorridos no se contabilizan como usados.

Una sonda auxiliar posterior de 96 llamadas registró asignaciones Python mediante tracemalloc: mediana del pico por llamada R4 110.643,5 bytes y R5 101.752,5 bytes. No mide RSS ni toda la memoria nativa. Sin calentamiento, su primera llamada puede incluir inicialización diferida: **no se usa el máximo de esa sonda para afirmar una mejora comparable** ni como criterio de selección. Código y filas se conservan en scripts/memory_probe.py y evidence/memory.json.

## Qué queda pendiente

| Área | Estado |
|---|---|
| Recorrido de pruebas + ingreso local | Implementado, comparación y regresión aprobadas en corpus sintético |
| Picos locales | Mejoraron en las 3 repeticiones; sin cota temporal de ejecución ni garantía bajo carga de producción |
| Testigo real completo | Falta prueba autenticada de cuenta y storage; no se hizo otra llamada RPC tras el 403 de R4 |
| Cadena canónica y layout | Raíz fijada por política no prueba consenso ni atestigua runtime |
| Tercer Ojo | Solo escenarios condicionales; precio supuesto, interés desconocido bloqueado |
| Oráculo/IRM/EVM | No ejecutados ni validados en esta etapa |
| Gas, financiación y no recurso | Se mantiene la autorización cerrada; resolución externa separada de NQC031/032 |
| Recepción de red/builder/inclusión | No medidos ni habilitados |

Los 1,40 ms corresponden al paquete ya recibido en memoria, su verificación y escenario local. No sustituyen las mediciones del filtro preparado, del motor R2, del bot extremo a extremo ni de rentabilidad. El objetivo <=5 ns sigue sin demostración y no es pertinente a esta verificación criptográfica completa. Las referencias previas NQC019 y las cinco capas de latencia no se reclasifican.

Recomendación: conservar R5 para pruebas offline y usar el importador para el siguiente testigo técnico autenticado que esté autorizado y disponible. Validar luego ese estado y su layout/oráculo/ejecución antes de integrar a una ruta observada; volver a medir con ese corpus y límites explícitos. No iniciar otra investigación de rentabilidad o financiación. No se cambian presupuestos para hacer pasar datos ni se compran recursos.

## Artefactos

`PRE_REGISTER.md`: criterio previo; `evidence/benchmark/raw.zip` y `result.json`: muestras y entorno; `scripts/verify_results.py`: reconstrucción; `STABILITY.json`: resultado local y bloqueos; `PROVENANCE.json`: procedencia; `SHA256SUMS`: hashes de todos los archivos salvo el propio manifiesto. README contiene reproducción e importación. Fuentes/evidencias base, R1, R2, R3 y R4 verificadas intactas (76/47/49/59/57 archivos).

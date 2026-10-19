# NQC 666 R7 — recepción acotada, estado auténtico aún pendiente

**Resultado:** se implementó y probó una frontera opcional de recepción fragmentada. R5 sigue predeterminado, sin modificar sus fuentes ni reactivar las variantes rechazadas en R6. No se integró un testigo auténtico y no está estabilizado el bot completo.

Base: `e5842cc676c93c99f08025ae22537fcc8a041fca`. Solo se añade r7-stream-ingress; main y R0–R6 permanecen intactos.

## Evidencia nueva y bloqueo

El paquete NQC_031_R2_ONCE_VALORES_Y_DOS_CONTRATOS.zip tiene SHA256 `82eeaeb53e2ba9563400898536854318ce65b6c805873d3f7de98a1882792a86`. Sus **200 archivos** cumplieron el manifiesto. El informe actual declara las 82 lecturas cubiertas y 11 valores recuperados de eventos, pero **0 pruebas de cuenta, 0 pruebas de almacenamiento y raíz exacta pretransacción null**. No se encontró ningún payload JSON accountProof/storageProof en ese archivo. La integridad del paquete no autentica esos valores.

El objetivo de ese frente es chainId 4663, bloque 66744162, antes de tx índice 1. R5 admite Ethereum chainId 1 al final de bloque. No se sustituye el preestado Nitro por el bloque padre/final, ni se inventan pruebas. Se conservan seis documentos técnicos originales y sus hashes; no se ejecutan contratos ni se repite financiación/auditoría.

## Ingeniería entregada

- Una captura activa, un buffer acotado y un propietario; sin servicios, hilos nuevos ni dependencias.
- Revocación inmediata del resultado anterior al empezar una actualización. Identidad opaca de captura/recibo, offsets exactos y rechazo de duplicados/huecos/fragmentos mutables.
- Límites de 2 MiB, 1024 fragmentos, 50 ms de captura y 5 ms de escenario. Caducidad monotónica fijada al comienzo; no se reinicia al llegar el último fragmento.
- R5 verifica encabezado, identidad, código, cuenta y los nueve slots. La puerta comercial sigue cerrada; el precio supuesto nunca se convierte en observado.
- Importador offline con conservación de bytes/hashes y benchmark por fases. Los hashes de salidas se reconstruyen independientemente con enteros Python.

El plazo de captura empieza al inicializar el buffer tras la revocación inicial. La ventana externa sí incluye la llamada completa desde antes de begin/reset. Los plazos rechazan resultados cuando vuelve el control, sin preempción. Si deja de llegar tráfico, no hay temporizador de fondo: el buffer queda acotado y sin resultado anterior utilizable; abort permite cancelarlo.

## Mediciones

UTC: 2026-10-19T02:30:34Z a 2026-10-19T02:31:39Z. 36.864 ventanas, tres repeticiones, 6.144 por perfil/variante. 16 fixtures originales y 13 precios condicionales; los datos y el runtime de fixture son **sintéticos**, no Morpho desplegado ni una muestra representativa del mercado.

CPU AMD EPYC 9V74 bajo KVM, afinidad CPU 0, Python 3.12.14, GC habilitado; Rust 1.90.0/LLVM 20.1.8, O3/fat LTO. Frecuencia/carga/IRQ del host no controladas. Se conserva cpuinfo y calibración; su mediana fue 201–210 ns y su máximo 199.366 ns, sin restar ni eliminar muestras. No se atribuye causalidad a la VM.

La ventana parte de fragmentos ya preparados en memoria e incluye ensamblaje, prueba, escenario Rust, autorización cerrada e instrumentación. Excluye fragmentación inicial, archivo, red/HTTP, colas externas, oráculo/IRM/EVM y builder. **No mide latencia real de extremo a extremo.**

Tiempos totales en ns; todos los máximos y descartes están incluidos:

| Fragmentos | Ruta | Mediana | p95 | p99 | p99.9 | Máximo |
|---|---|---:|---:|---:|---:|---:|
| single | r6_join | 1,557,268 | 2,340,644 | 2,953,546 | 4,734,266 | 20,544,428 |
| single | r7_stream | 1,592,069 | 2,373,002 | 2,993,896 | 5,192,398 | 13,036,644 |
| 4096 | r6_join | 1,581,875 | 2,430,407 | 3,183,078 | 5,989,510 | 12,707,414 |
| 4096 | r7_stream | 1,630,587 | 2,481,204 | 3,227,995 | 5,153,561 | 8,016,322 |
| 257 | r6_join | 1,556,557 | 2,313,533 | 3,129,478 | 6,139,288 | 8,434,013 |
| 257 | r7_stream | 1,804,716 | 2,681,361 | 3,781,369 | 5,832,501 | 13,015,181 |

**0 descartes** en ambas rutas. Esto no garantiza ausencia de picos futuros. Los percentiles p99.9 por perfil se apoyan en apenas unos pocos valores de cola; no son cotas probabilísticas certificadas.

R7 añadió 3,08% de mediana con 4096 bytes y 15,94% con 257 bytes. Con 257 bytes, p99 subió 20,83% y máximo 54,32%; con un fragmento, p99.9 subió 9,68%. Las reducciones de algunos máximos no se anuncian como mejora. **No se promueve una optimización**: R6+join y R7 tienen defensas distintas; la comparación cuantifica el coste de ampliar la frontera de validación.

Con fragmentos de 4096 bytes, las medianas por fase fueron:

| Ruta | Ensamblaje | Verificación | Escenario | Autorización |
|---|---:|---:|---:|---:|
| r6_join | 3,786 | 1,549,086 | 24,607 | 2,053 |
| r7_stream | 26,709 | 1,562,726 | 29,634 | 5,097 |

Las medianas de fases no suman necesariamente la mediana del total; se comprueba la suma exacta **por cada ventana individual**. El parseo y las pruebas dominan este recorrido. No se fuerza ni ensaya 5 ns para este componente.

## Pruebas y trazabilidad

La reproducción limpia aprobó **163 ejecuciones de funciones de prueba**: 21 nuevas R7, 51 R6, 75 R5, 7 Rust y 9 aislamiento. Incluye equivalencia de los 16 paquetes en tres fragmentaciones; reloj congelado/caducidad, plazos, truncación, duplicados, mezcla de bloques/cadenas, memoria/tamaño, recibos copiados, hilos ajenos, reentrada e interrupción. El nuevo paquete real incompleto fue rechazado. No son 163 pruebas nuevas independientes.

Las 36.864 ventanas conservaron resultado observable, estado y orden. verify_results reconstruye todas las distribuciones/fases, semillas y descartes, y cada digest de salida con aritmética entera Python. Se verificaron los manifiestos R0–R6 y el aislamiento (0 workflows activos, 106 deshabilitados).

Biblioteca Rust reconstruida, igual a R5/R6: SHA256 `1cc575699de5a9395dc95b6cc17fbabae0c355459948ba91ef11d204ef0388f4`. Los hashes de fuentes/entradas figuran en evidence/benchmark/result.json; SHA256SUMS cubre la entrega salvo sí mismo.

## Continuación y límites

Conservar R5 y no reabrir la optimización rechazada en R6. El siguiente bloqueo real es el testigo completo definido en ../r6-witness-ingress/WITNESS_REQUIREMENTS.md: cuenta/storage/runtime a una raíz con anclaje independiente y cadena/punto de estado correctos. Luego verificar layout, oráculo, intereses y ejecución sobre datos auténticos y medir recepción–candidato–builder. Hasta entonces, ninguna admisión comercial.

No hubo RPC nuevos, reintentos del 403, cambios de ruta para eludirlo, operaciones públicas, firmas, despliegues, gasto ni cambios a main. No se ejecutó nuevamente el corpus histórico Solidity/EVM no afectado ni se validaron condiciones financieras externas. La entrega cierra pruebas locales del adaptador, no la estabilidad integral.

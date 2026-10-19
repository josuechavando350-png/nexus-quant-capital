# NQC666 R3 — contrato de medición

Se conserva R2 en `43e1761caec3d45dedd08c177b51f97e066fe075`, sin modificar
sus fuentes ni evidencia. Este experimento añade una etapa diferente: verificar
pruebas de estado antes de preparar cálculos. No se comparará su tiempo como si
fuera equivalente a los 621 ns del pipeline sintético R2.

Hipótesis: dentro de un mismo paquete EIP-1186 se repiten nodos de almacenamiento.
Decodificar y validar cada nodo idéntico una sola vez reduce el coste sin omitir
la comprobación de pertenencia de ninguna ruta. La caché nace y muere dentro de
`verify`; no reutiliza resultados entre paquetes, raíces, bloques o políticas.
`shared=False` es el control con las mismas comprobaciones y bibliotecas.

Corpus: 16 testigos **sintéticos**, 9 slots por posición, 0/16/64/256 entradas de
relleno, 4 casos de cada tamaño. Cada raíz se contrasta con un constructor MPT
independiente. Una ausencia demostrada corresponde al IRM nulo; un testigo ausente
no equivale a cero. El bytecode sintético no es Morpho desplegado. Se conserva
además un encabezado histórico real, que debe validar su hash pero seguir bloqueado
por falta del testigo de cuenta/almacenamiento.

Matriz final: 4.096 llamadas individuales × 3 repeticiones × 2 variantes × 2 modos
= 49.152 ventanas. Orden de corridas intercalado con semilla 666304. El corpus y
las hipótesis se fijan antes de medir. No se selecciona la repetición más rápida.

- `verify`: bytes ya recibidos → JSON, esquema, reloj, encabezado, Keccak/RLP/MPT,
  cuenta, código, nueve slots, identidad de mercado, consistencia y hechos inmutables.
- `ingress_scenario`: además incluye reset del ancla, invalidación, ticket, comprobación
  de vigencia, IPC local hacia el evaluador Rust R1 ya iniciado, cálculo condicional
  con precio supuesto y denegación explícita de autorización. No hay candidato observado.

Los buffers, políticas y proceso Rust existen antes de la ventana. Selección del
caso y todas las operaciones indicadas están dentro. El hash del resultado observable
completo se consume después de detener el reloj; su serialización diagnóstica no se
presenta como incluida. Se exige igualdad del resultado entre variantes/repeticiones.
Las métricas internas de número de decodificaciones se excluyen de esa igualdad.

Reloj CLOCK_MONOTONIC_RAW, controles de dos lecturas por muestra, sin restar overhead,
recortar picos ni dividir lotes. CPU fijada a un procesador permitido; frecuencia,
hipervisor, interrupciones y carga externa no controlados. GC Python permanece activo.
Se publican muestras crudas, mediana, p95, p99, p99.9 y máximo. En cada distribución
agrupada hay 12.288 muestras: p99.9 representa aproximadamente 12 observaciones de cola,
no una garantía operacional. La correlación temporal impide tratarlas como muestras
independientes para inventar intervalos de confianza.

Aceptación: pruebas funcionales/adversariales iguales en ambas rutas, raíces y slots
contrastados, baseline intacto, resultados observables idénticos y ahorro medido.
Se reportarán también las regresiones de colas. Esta etapa no tiene un presupuesto
impuesto de 700 ns: autenticación criptográfica y decisión preparada tienen costes
y fronteras diferentes. No se declarará consenso, frescura del oráculo, ejecución
Morpho completa, financiación ni admisibilidad comercial.

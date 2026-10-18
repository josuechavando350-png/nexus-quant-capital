# NQC666 R1 — comparación previa a las mediciones

La hipótesis concreta es reducir el coste de las divisiones exactas U256 al usar
la representación nativa cuando cabe, división por un limb y la identidad
`floor(floor(n/10^18)/10^18) = floor(n/10^36)`. La referencia conserva la misma
semántica con multiplicación de cuatro limbs y división binaria general.

No se cambia el control de overflow de Solidity: el producto y la suma previa
al redondeo hacia arriba deben caber aunque el cociente matemático quepa.

Medir tres repeticiones intercaladas por semilla de math, adapter y pipeline,
200.000 llamadas por repetición, 256 entradas sintéticas de magnitudes variadas
y resultados variables. La ruta completa incluye copia del update, matemática,
validación de snapshot, evento, selección y verificación financiera final.
No incluye adquisición/parsing de red, IRM auténtico, EVM, firma o builder.

CLOCK_MONOTONIC_RAW, 10.000 controles de reloj vacío, entradas y resultados
observables mediante black_box; checksum consumido después de cerrar cada medida.
Afinidad sólo a una CPU permitida, sin modificar el sistema. Guardar todas las
muestras little-endian, hashes, p50/p95/p99/p99.9/máximo y el entorno. Sin restar
reloj, eliminar outliers ni sumar percentiles. Validar primero paridad exacta.

El objetivo de 5 ns corresponde al filtro previo del corte inicial y no se
atribuye a esta aritmética U256. Estos resultados son una nueva serie separada.

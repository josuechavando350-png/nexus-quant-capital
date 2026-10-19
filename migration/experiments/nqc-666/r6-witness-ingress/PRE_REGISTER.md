# R6: integración de testigo, sin confundir disponibilidad con autenticidad

Base R5: `205015f4941abaad2c3102a4dbffd4e980f62196`. Solo carpeta R6.
El inventario inicial no encontró testigo auténtico completo. NQC031 declara
captura incompleta/no autenticada, cadena 4663, raíz pretransacción desconocida,
0 pruebas de cuenta/storage verificadas. No se convierte a Ethereum ni se
reconstruyen sus contratos/financiación. No se repite la llamada RPC con 403.

Integración: captura JSON-RPC offline con 4 lecturas documentadas, fijadas a hash
de bloque, respuestas correlacionadas por ID, cobertura exacta. Se permite
normalizar el ancho de claves storage; nunca valores desconocidos ni pruebas.
Política externa fija cadena/bloque/mercado/prestatario/código. requireCanonical
en una solicitud es una condición documental, no evidencia de consenso.
Solo end_of_block Ethereum/Pectra soportado por R5; Nitro/pretx se rechazan.

Dos hipótesis separadas: A) evitar serializar/reparsear el paquete entre adapter
y R5; B) reemplazar regex hex por fromhex + round-trip canónico. RLP estricto,
hashes, caminos, slots, identidad, vigencia y defensas del gateway se mantienen.
Sin caché entre paquetes, nuevos hilos, dependencias ni procesos de ejecución.

Pruebas: equivalencia de decodificación hex incluyendo caracteres no válidos,
espacios, Unicode, tamaño; suite R5 y pruebas del adaptador (duplicados, ID bool,
errores, respuestas parciales, reorg, mezcla de bloques, datos sin prueba,
cancelación, plazos). Comparar AST del cuerpo semántico y defensas con R5,
exceptuando parseo, selección explícita de decoder e inyección del verificador.

Matriz: 3 repeticiones × 2048 grupos × 3 variantes × 2 modos. Variantes:
baseline (R5 + serialización), object (solo A), optimized (A+B). Modos:
verificación wire; ingreso local completo con reset, wire, prueba, ticket,
escenario Rust y autorización cerrada. 16 paquetes sintéticos R3, 13 precios,
orden de inputs barajado, variante inicial rotada entre grupos. Afinidad a una
CPU, GC habilitado. CLOCK_MONOTONIC_RAW individual; 2 lecturas de calibración
por grupo; no recortar picos ni descartar muestras fallidas. Guardar orden,
estados, tiempos, hashes de resultados, CPU/herramientas/configuración.

Criterio de selección, antes de medir: salidas aceptadas equivalentes, defensas
aprobadas; mediana >=5% menor que baseline en cada repetición y modo; p99,
p99.9 y máximo agregados <=105% baseline en ambos modos; cero descartes
adicionales frente a baseline. Si falla, no promover la optimización. Comparar
optimized con object para atribuir B, sin ocultar una regresión de B. Los tres
caminos permanecen explícitos para diagnóstico, nunca seleccionados por datos
de entrada. Un pase local no certifica estabilidad integral.

Si ambas alternativas cumplen, elegir optimized solo si también mantiene p99,
p99.9 y máximo <=105% de object en ambos modos y mediana de ingreso agregado
menor; de lo contrario elegir object. Si ninguna cumple, baseline sigue por
defecto. La API/CLI conserva baseline como valor por defecto independientemente
de resultados; cualquier camino experimental elegido se solicita explícitamente.

La latencia e2e de red/builder y la integración auténtica permanecen sin medir
si no aparece un testigo completo. El objetivo 5 ns sigue limitado al filtro
preparado de versiones previas: no se atribuye a JSON/Merkle/oráculo/EVM.

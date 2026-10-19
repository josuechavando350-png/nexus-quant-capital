# R5 — hipótesis y criterio previos a medir

Base inmutable: R4 `488ba082a7e5f779c2a675b4089974615da88a92`.
Hipótesis: conservar los nodos ya decodificados/validados y observar un único
recorrido de py-trie reduce el coste del ingreso sin cambiar su aceptación.
No se añade dependencia, hilo, proceso, RPC ni caché entre paquetes.

Se preservan exactamente los cuerpos verify/_verify de R3 y StableGateway/Ticket
de R4. Solo se cambia la resolución del verificador y del decodificador. La
comparación de fuente y AST es parte de las pruebas. La biblioteca Rust R4 y el
cálculo R1 no cambian. La caché pertenece a cada paquete; cada prueba tiene su
propio conjunto de nodos disponibles/usados. Un nodo de otra prueba o un hermano
embebido que no se recorre no puede suplir una prueba faltante o sobrante.

Pruebas previas: corpus R3, suite adversarial R3 en ambos verificadores, defensas
R4 en ambos gateways, casos dirigidos a nodos inline/ausencia/prueba incompleta,
y diferencial determinista de árboles generados. Todos los resultados válidos
deben coincidir y las entradas inválidas deben rechazarse. No se promueve ningún
estado desconocido a hecho observado ni se abre autorización comercial.

Medición: 3 repeticiones de 4096 pares por modo (verificación e ingreso completo
local). 16 paquetes sintéticos R3, 13 precios condicionales, orden de entradas
barajado con semilla fija, variante inicial alternada. R4 y R5 en el mismo proceso
y CPU, GC habilitado. Calentamiento fuera de ventana, cada operación completa
individual dentro. Ingreso incluye reset, prueba, ticket, escenario Rust y puerta
de autorización cerrada. Verificación incluye JSON, encabezado, cuenta y 9 slots.
No incluye adquisición/red/builder/EVM/oráculo/IRM ni verificación financiera.

Reloj CLOCK_MONOTONIC_RAW, calibración de dos lecturas por pareja; sin restar
overhead ni recortar muestras. Se guardan todos los tiempos, rechazos, secuencia,
resultados observables y hashes. Mediana, p95, p99, p99.9, máximo y deltas pareados.
KVM no ofrece cota temporal de ejecución; los presupuestos R4 descartan resultados
tardíos, sin interrumpirlos. No se atribuirá una regresión a la VM sin evidencia.

Selección provisional: equivalencia exacta y mediana al menos 10% menor en cada
repetición de ambos modos. Para considerar resuelta la regresión de colas de esta
muestra, p99, p99.9 y máximo agregados deben ser <=105% del baseline por modo.
Un resultado que falle este criterio se conserva como evidencia, no se retoca el
umbral ni se anuncia estabilidad. Pasar esta muestra tampoco certifica estabilidad
del bot completo: falta testigo real, oráculo/ejecución y validación externa.

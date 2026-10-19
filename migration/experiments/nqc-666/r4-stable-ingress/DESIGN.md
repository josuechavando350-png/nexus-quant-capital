# R4 — integrar y fallar de forma controlada

## Alcance concreto

R4 conecta el verificador de pruebas R3 con las fórmulas Rust R1 dentro del mismo
proceso. Añade un importador offline de paquetes y política, tickets ligados a una
instancia, caducidad monotónica y rechazo de resultados tardíos. No cambia las fuentes
de R1, R2 o R3, ni traslada resultados de investigación a autorización comercial.

**El testigo real completo todavía no está incorporado.** Las ramas técnicas revisadas
no aportaron uno nuevo. El intento de consultar un encabezado público desde este entorno
devolvió HTTP 403 y se detuvo. Se conserva la solicitud/error en evidencia, sin llamarlo
respuesta de cadena, sin reintentos por otra ruta, credenciales, nuevos servicios o
activación de workflows. El rechazo de un proveedor no se remedia inventando estado.

## Problemas reproducidos de R3

1. Dos instancias con igual época y hash de bloque generaban tickets con los mismos
   campos. Una instancia aceptaba el ticket de la otra. Esto no autorizaba trading
   —la admisión seguía siendo falsa—, pero no preservaba la identidad de la instancia.
2. `MathWorker.health` esperaba una línea sin límite temporal. Un worker silencioso
   mantuvo bloqueado al llamador durante la ventana de observación de 250 ms. La prueba
   termina ambos procesos explícitamente y conserva el resultado.
3. La caducidad dependía del `now_s` proporcionado. Un llamador que repitiera el mismo
   valor podía mantener un ticket válido en el gateway más tiempo que su vigencia real.

Son límites del prototipo local; no se presentan como explotación de un contrato ni
como pérdida financiera observada. Los scripts de reproducción solo usan fixtures y
procesos propios de laboratorio.

## Integración Rust

`nqc666_health(Request) -> Response` exporta una ABI C por valor. Seis números U256
entran como 24 limbs u64; salen estado, deuda, capacidad y elegibilidad condicional.
Las estructuras tienen layout `repr(C)`, tamaños 192 y 80 bytes, comprobados en Rust
y Python, y versión de ABI explícita. No hay punteros recibidos del llamador, buffers
persistentes, asignaciones de heap, I/O ni bloque `unsafe` en el wrapper Rust.

Las fórmulas se importan directamente de R1. Se conservan redondeos, errores de overflow
y límites de representación. Un error devuelve campos numéricos cero además del código;
el binding rechaza el resultado y no reutiliza una salida anterior. Cada llamada crea
su propio request; el ensayo concurrente solo comprueba ausencia de buffers compartidos,
no introduce paralelismo en el motor.

`NativeMath` exige un SHA-256 configurado antes de cargar la biblioteca. Ese hash
garantiza coincidencia con el binario fijado, **no procedencia ni aislamiento**. El código
y sistema de archivos locales se consideran de confianza; un reemplazo hostil entre
hash y carga está fuera del modelo. Las rutas de biblioteca nunca vienen del paquete
de mercado. La carga, resolución de símbolos y comprobación de hash no están en el
benchmark de llamadas, y así se documenta.

El cambio elimina el pipe y el proceso hijo del camino R4. La biblioteca comparte
proceso con Python: un defecto nativo o fallo fatal del runtime puede terminar ese
proceso. El perfil usa `panic=abort`; no se promete recuperación de un panic cruzando
la ABI. Se mitiga con interfaz sin punteros, aritmética comprobada y contraste de casos,
pero no se declara una prueba formal de seguridad de `ctypes`, LLVM o sus bibliotecas.

## Tickets y coherencia

`StableGateway` pertenece a un objeto hilo concreto. Un ticket contiene sesión,
época, bloque, mercado y prestatario; además se exige que sea exactamente el objeto
emitido y actualmente retenido. Una copia, reconstrucción o ticket de otra instancia
se rechaza. No es un formato serializable para transmisión entre servicios.

Cada ingreso invalida antes de verificar. Reset, fallo de prueba, reloj inválido,
resultado inconsistente, excepción o cancelación (`BaseException`) eliminan el snapshot.
Un intento de reentrada revoca el estado, y se comprueba de nuevo después del cálculo
que el ticket no haya sido revocado. Un acceso desde otro hilo se rechaza sin cambiar
el estado del hilo propietario. No se introducen locks, colas o workers de búsqueda.

El llamador sigue suministrando una hora de observación confiable. R4 añade una fecha
de expiración sobre `time.monotonic_ns()` a partir de la vigencia restante del snapshot.
Repetir `now_s` ya no congela esa expiración. Se comprueba antes y después del cálculo;
también se rechazan retrocesos de ambos relojes. No se detecta que la política inicial
o la hora original sean falsas: son entradas del llamador de confianza. El modo offline
de replay usa una hora histórica explícita y siempre conserva admisión falsa.

## Plazos y disponibilidad

El valor inicial es 50 ms para verificar un paquete y 5 ms para un escenario preparado.
Si una operación termina tarde, su salida no se utiliza y el snapshot se elimina.
**Esto no limita cuánto puede tardar la CPU.** Las comprobaciones de tiempo no pueden
interrumpir al hipervisor, al kernel, a una llamada nativa o al verificador en curso.
Un supervisor operativo todavía no está implementado.

Estos límites intercambian disponibilidad por vigencia. Una pausa del host puede causar
un descarte correcto de un paquete válido. Los benchmarks guardan cada latencia,
incluidos los descartes; no se calculan percentiles únicamente sobre éxitos. La
recuperación de un intento rechazado se mide aparte, cuando ocurre. No se llama
“latencia estabilizada” a esconder intentos tardíos detrás de un error.

La saturación de entrada, backpressure, persistencia, recuperación tras caída del proceso,
aislamiento físico de CPU y garantías de cola no se han implementado ni medido aquí.
No se alteraron prioridades, frecuencia, IRQ o configuración original del entorno.

## Importación de evidencia

`scripts/import_witness.py` recibe un paquete en el esquema estricto R3 y una política
separada. Conserva ambos archivos originales, hashes, hora de replay, resultado y motivos
de rechazo. El directorio debe ser nuevo. Un fallo no entrega hechos o predicciones
parciales. La CLI no consulta RPC ni crea sus propios pins desde el paquete recibido.

La política debe venir de una decisión independiente y confiable del operador. Una CLI
no puede certificar que quien aporta una política dice la verdad. `ROOT_BINDING_VERIFIED`
solo expresa pertenencia a la raíz fijada. `canonicality=unknown`, la asociación entre
runtime y layout permanece como supuesto de política, y `oracle_price` y elegibilidad
observada permanecen desconocidos.

La prueba positiva utiliza un fixture **sintético etiquetado**. La prueba negativa mezcla
un encabezado histórico real con una prueba de cuenta faltante y exige rechazo; eso no
es un testigo real reconstruido. No se rellena ningún dato ausente con una estimación.

## Protecciones que siguen fuera del alcance

Un escenario puede calcular deuda/capacidad únicamente cuando el estado ya está acumulado
al timestamp del bloque y se suministra explícitamente un precio supuesto. No se ejecuta
oráculo ni IRM; no se convierte la predicción en observación. No hay simulación de una
liquidación, ruta de venta, financiación/no recurso ni pagos de builder/proponente.

`authorize` sigue devolviendo `commercial_admission=False` y `observed_candidate=None`.
Es una puerta cerrada de investigación, no el reemplazo de los guardianes financieros
originales. Los tests del motor base/R1/R3 y hashes previos se conservan. NQC031/032,
main, configuraciones originales y otros repositorios permanecen fuera de las escrituras.

Fuentes de ABI consultadas:
[Rust: layout de tipos](https://doc.rust-lang.org/stable/reference/type-layout.html),
[Python 3.12: ctypes](https://docs.python.org/3.12/library/ctypes.html).
Fuentes de la consulta de datos:
[endpoint público documentado](https://ethereum.publicnode.com/),
[especificación eth_getProof](https://ethereum.github.io/execution-apis/api/methods/eth_getProof/).

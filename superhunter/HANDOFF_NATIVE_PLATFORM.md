# Continuidad — aceptación nativa obligatoria

Base local: `SUPERHUNTER_efectos_evm_1603.zip`, carpeta `codigo/`.
SHA-256 de esa base: `629aafb6486e42e35b44d2944672ae43c36936575544ce26e68ec57518cdf60a`.

La base contiene 1,603 identificadores distintos de pruebas y separaba la
aceptación EVM del comando de revisión general. Esta entrega agrega
`native_platform.py` y su suite a la CLI y al registro de QA, sin cambiar los
contratos del laboratorio, EVM, conciliador ni analizador de fuentes previos.

La ruta nueva no es un launcher de investigación de terceros. Solo ejecuta la
suite propia y los controles nativos fijos existentes, y exige replay. Un paquete
parcial o una ejecución sin herramientas no produce informe aprobado.

Los cinco archivos nativos y los catálogos 27/50/25 permanecen byte a byte.
No aplicar este incremento directamente sobre un PR que solo contenga una parte
del acumulado. El diff se prepara contra esta base local exacta. La publicación
remota completa, las ramas concurrentes, los conectores activos y el benchmark
independiente de descubrimiento siguen pendientes.

No hay autorización para nuevas suscripciones, firmas/transacciones en cadena,
cuentas, main, workflows ni interacción con Cano, Vercel u otros repositorios.
No se ejecuta la suite histórica completa NQC o su verificador global de
islamiento al disponer únicamente de este paquete acumulativo. Registrar cada
resultado real, fallo e intento incompleto en VALIDATION.json de la entrega.

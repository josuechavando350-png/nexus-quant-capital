# NQC040 — adquisición acotada entre reinicios

Se añadió una capa de sesión para el plan y los verificadores originales
NQC037/038. **No se adquirieron pruebas históricas ni se enviaron consultas RPC.**
Este cambio prepara el ejecutor; no requiere que Chavando use una computadora.

## Hallazgo reproducible

El límite anterior se aplica a una invocación. Nueve invocaciones de
`intake.execute()` con carpetas nuevas y un transporte simulado que siempre falla
producen nueve intentos de la primera solicitud. Cada invocación cumple su límite
individual, pero no existe un contador común para la adquisición autorizada.
No se afirma que hayan ocurrido esos intentos contra Triport: el caso es offline.

Esto importa al reanudar un trabajo cuyo permiso es de **ocho lecturas en total**.
NQC039 exige una carpeta nueva y no implementa reanudación entre invocaciones.
No se modifica ni se sustituye silenciosamente ese paquete publicado.

## Corrección y comprobaciones

`session.py` envuelve el plan fijo NQC038 y llama al verificador NQC037 sin
cambiar sus objetivos, raíces, métodos ni condiciones de aceptación:

- Inicialización explícita y offline. Reanudar nunca crea un presupuesto nuevo.
- Reserva persistida mediante escritura, `fsync`, reemplazo atómico y `fsync`
  del directorio **antes** de invocar el transporte.
- Máximo de ocho reservas ordenadas; una reserva ambigua consume su lugar y
  bloquea la sesión. No se intenta adivinar si una solicitud llegó al proveedor.
- Respuestas guardadas por SHA-256 y revalidadas desde el principio antes de
  cualquier solicitud adicional. Una interrupción tras guardar una respuesta
  permite verificarla offline; no vuelve a pedirla.
- Primer error de transporte, envelope o prueba: sesión detenida. Reiniciar no
  habilita otro intento. Un error de persistencia también detiene la ejecución.
- Bloqueo POSIX exclusivo, probado con un segundo proceso, para una sola sesión.
- Vinculación del plan, fuentes e inputs por SHA-256; cambios o archivos ausentes
  detienen la ejecución antes de usar red. Los hashes no son firmas de autoridad.
- Rechazo de reflejos literales de la clave en una respuesta antes de persistirla;
  no se guardan mensajes arbitrarios de excepciones ni cuerpos de errores RPC.

Las 17 pruebas nuevas cubren esos casos y la integración con el adaptador real
NQC038 sobre un opener simulado. Las primeras dos respuestas de esa integración
usan el chain ID esperado y la cabecera padre previamente capturada; la prueba
inválida de la tercera respuesta detiene la secuencia. La comprobación de ocho
pasos sustituye explícitamente el verificador por un mock para aislar el contador:
**no produce ni acredita pruebas Merkle históricas**.

## Frontera operativa aún pendiente

La garantía vale para **un directorio de sesión confiable y persistente**.
No es un contador distribuido, ni resiste que alguien borre, restaure una copia
antigua, duplique o sustituya deliberadamente el registro. `flock` protege un
filesystem POSIX compartido; no coordina dos hosts con copias independientes.
La durabilidad depende del filesystem y su implementación de `fsync`.

Por tanto, este módulo **todavía no autoriza ejecutar desde un disco temporal**
que podría desaparecer entre turnos. Falta establecer un único almacenamiento
operativo durable y acceso seguro a la credencial. Si cualquiera de los dos se
pierde o queda ambiguo, se detiene la adquisición; no se inicializa otra sesión
para obtener ocho consultas adicionales. No hay sesión real creada en este
experimento, únicamente directorios temporales de pruebas ya eliminados.

No existe una nueva vía de transferencia de credenciales en las herramientas
expuestas en esta ronda. No se repitió la transferencia fallida ni se reveló la
clave. El panel previo mostró Robinhood LIVE después de cargar; su estado
PREVIEW inicial no constituye un fallo. El acceso histórico del proveedor
permanece sin probar.

## Uso por el ejecutor, una vez resueltos los requisitos

API Python, no instrucciones de instalación para el usuario:

1. `initialize(directory)` crea una sesión solo una vez, offline.
2. `run(directory)` inspecciona y revalida sin red; es el modo por defecto.
3. `collect(key, directory, max_new_requests=...)` usa la clave únicamente en
   memoria y el transporte NQC038. El límite por llamada se suma a las reservas
   anteriores; nunca reinicia el contador de ocho del mismo registro.

No se añade CLI de credenciales, endpoint alternativo, firma, envío de
transacciones, workflow, servicio ni despliegue. La capa nueva solo admite el
plan original; no amplía el permiso de lectura. Incluso un paquete completo
mantiene `commercial_admission=false` y no demuestra preestado exacto, consenso
independiente, replay Nitro ni rentabilidad.

## Validación y siguiente cuestión

`VALIDATION.json` y `evidence/*.log` conservan los resultados ejecutados:
17 pruebas de sesión, 32 del verificador, 7 del transporte, 2 del exportador,
9 de aislamiento, más el verificador de aislamiento. No se volvió a ejecutar
el análisis de blobs NQC036, Rust, Nitro ni pruebas económicas.

Las fuentes previas permanecen byte por byte en el commit base
`cc5ce6e1eb32201f031653b5f15ffaf4d7e8516e`. El manifiesto de este directorio cubre
solo los archivos de esta entrega; no es evidencia on-chain.

La siguiente revisión offline útil es precisar el mapa de lecturas de `tx0`:
derivar de las fuentes Nitro fijadas los slots raíz y las dependencias dinámicas
de blockhashes, cola de retryables y precios L2. NQC037 ya explica sus efectos;
no repetir ese resumen. Producir selectores calculables y distinguir los que
dependen de valores aún no autenticados, sin ampliar ni ejecutar el plan de ocho
consultas y sin afirmar que una lista estática completa un witness.

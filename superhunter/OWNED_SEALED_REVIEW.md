# Lectura de fuente propia después del filtro

El worker anterior (`owned_restricted_worker.py`) captura su copia antes de
activar seccomp. Este incremento añade una ruta distinta y conserva ese perfil
y sus expedientes históricos. No ejecuta código recibido ni acepta destinos,
comandos, URLs o repositorios elegidos por el operador.

## Flujo implementado

1. El padre captura dos veces el repositorio que contiene este módulo y exige
   igualdad de bytes y modos. Comprueba la política de integridad histórica.
2. Serializa un paquete binario canónico: versión fija, cantidad de archivos,
   nombres relativos, modos cerrados y bytes. Es una representación de datos;
   los nombres nunca se usan como rutas de extracción.
3. Crea un memfd y aplica `F_SEAL_WRITE`, `F_SEAL_GROW`, `F_SEAL_SHRINK` y
   `F_SEAL_SEAL`. Abre una descripción de solo lectura con offset cero y cierra
   la descripción de escritura. No hay archivo de checkout en el hijo.
4. El supervisor existente inicia un proceso dedicado, entrega ese descriptor
   como FD 0 y conserva su limpieza de grupo antes de recolectar al líder.
5. El hijo carga los módulos y la biblioteca seccomp fijada. Comprueba solo
   metadatos de FD 0 y exige que no haya descriptores extra. Instala el mismo
   conjunto de reglas restrictivas; no se amplía su permiso de llamadas.
6. Después de los controles del filtro, lee FD 0 hasta el tamaño exacto y EOF,
   decodifica el paquete y calcula la política de integridad en memoria. El
   hash del paquete y del inventario deben coincidir con los del padre.
7. El padre exige el orden filtro → lectura → revisión dentro de su intervalo,
   vuelve a comprobar fuente e intérprete y confirma limpieza antes de publicar.

Los perfiles nuevos son `owned-sealed-boundary-lab-v1`,
`owned-sealed-boundary-review-v1` y
`owned-linux-x86_64-sealed-input-compute-v1`. No son alias de los anteriores.
La prueba conserva `input_acquisition_inside_filter=false`, porque la captura
original del padre ocurre antes; delimita adicionalmente
`worker_payload_read_inside_filter=true`. Una respuesta no coincidente conserva
`OWNED_SEALED_LAB_INCONCLUSIVE` y no atribuye una observación positiva de lectura.

## Presupuestos y errores

- Hasta 4,096 archivos; 20 MiB por archivo y 64 MiB de datos en total. El marco
  añade 12 bytes de encabezado y hasta 1,031 bytes por entrada. Nombres de hasta
  1,024 bytes UTF-8 y 21 segmentos. Un inventario vacío se rechaza.
- Rechazo de claves repetidas o desordenadas, nombres inválidos, campos truncados,
  UTF-8 inválido, tamaños excedidos y bytes finales. Sin pickle ni deserialización
  de objetos ejecutables. Ninguna reserva usa directamente una longitud declarada
  sin comprobar el límite y los bytes disponibles.
- CPU del hijo 15 s; memoria virtual 256 MiB; espera del padre 30 s. La biblioteca
  se carga bajo 128 KiB por archivo y después el límite baja a 64 KiB. Salida de
  cada flujo: hasta 64 KiB. Los límites previos no se aumentan.
- Error de captura, fuente cambiada, salida excesiva o limpieza fallida impiden
  publicar una aceptación. Timeout y fallo observable del hijo conservan un
  expediente inconcluso. No hay alternativa de cálculo sin filtro.

## Uso y verificación

Con el entorno Python previamente fijado y el digest ejecutable calculado:

```sh
python -B -m superhunter check-owned-sealed-boundary \
  --source-digest DIGEST --out DIRECTORIO_NUEVO_FUERA_DEL_REPOSITORIO
python -B -m superhunter verify-owned-sealed-boundary \
  --source-digest DIGEST --bundle DIRECTORIO_DEL_EXPEDIENTE \
  --experiment-anchor SHA256_COMPLETE
```

El verificador reconstruye el paquete desde la fuente propia y exige manifiesto,
perfiles, identidades, límites, hashes, resultado, relojes y reporte exactos. No
ejecuta de nuevo al hijo. El expediente contiene observación, stdout, stderr,
resultado y revisión; no copia la fuente completa.

## Alcance de la evidencia

Los controles usan datos propios: entradas binarias, vacías y con Unicode;
prefijos truncados; tamaño declarado excesivo; sellos faltantes; escritura,
crecimiento y truncado reales denegados; descriptor extra; perfil histórico;
inversión temporal; promoción de reportes resellados y cambio antes de publicar.
La aceptación final y su digest se registran en `CONTINUATION.md` tras QA.

La adquisición del padre, el arranque de Python y la carga de módulos siguen
fuera del filtro. Los sellos restringen modificaciones del archivo de entrada,
no autentican su origen ni protegen por sí solos la memoria del intérprete.
Los hashes y tiempos son evidencia consistente declarada por procesos propios,
sin autenticación de host, productor o reloj. No hay protección afirmada frente
a otro proceso del mismo UID ni sandbox general de código hostil.

M1 permanece parcial. Este cambio no confirma vulnerabilidades externas ni
operación 24/7, y no integra scanners o candidatos del catálogo de 50.
La prueba de resistencia de seis horas sobre PR #108 conserva aquella fuente;
su duración y resultado no se transfieren a esta implementación.

Referencias de semántica consultadas: [memfd_create(2)](https://man7.org/linux/man-pages/man2/memfd_create.2.html)
y [F_GET_SEALS/F_ADD_SEALS](https://man7.org/linux/man-pages/man2/F_GET_SEALS.2const.html).
La disponibilidad del entorno se prueba realmente; nunca se eluden sus límites.

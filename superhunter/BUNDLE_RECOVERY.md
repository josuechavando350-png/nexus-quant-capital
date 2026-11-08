# Escritura interrumpida y salvamento de expedientes propios

Sucesor de PR #96 (`db1bdf457690cb21f8ce107bcc466b2d7c64eabe`).

Se reprodujo un defecto del escritor compartido: una entrada no válida creaba
la carpeta antes de validar todos los bytes; un reintento correcto fallaba con
FileExistsError. Ahora se copia y valida todo el payload y el tamaño del manifiesto
antes de crear directorios. También se rechazan nombres que el lector no admite.

## Publicación del marcador

Los archivos se escriben y sincronizan; se sincroniza el directorio. El marcador
se escribe primero en `.COMPLETE.pending` y se sincroniza antes de enlazarlo a
`COMPLETE.json`, sin reemplazar un nombre existente. Luego se retira el nombre
pendiente y se sincroniza otra vez el directorio. El formato y los bytes del
manifiesto normal no cambian; `.COMPLETE.pending` queda reservado al escritor.

Un corte durante el marcador deja el nombre pendiente, sin COMPLETE parcial.
Un corte después del enlace puede dejar ambos nombres: los lectores estrictos
de inventario lo rechazan y el nuevo inspector lo distingue como limpieza
pendiente. Nunca se retira ese archivo automáticamente del original.

Las pruebas instrumentan puntos de corte del escritor real y envían SIGKILL
al propio proceso; escrituras, flush, fsync y terminación son reales. Se prueban
cuatro cortes y un control normal. No son pruebas de apagón, caída del kernel o
durabilidad en cualquier sistema de archivos. Si falla una sincronización tardía,
pueden quedar bytes estructuralmente completos aunque el escritor no retorne
con éxito: el inspector no certifica el retorno o la durabilidad del escritor.

## Estados del inspector y códigos CLI

| Estado | Significado limitado | CLI |
| --- | --- | --- |
| INCOMPLETE_NO_MARKER | No se observó marcador; puede haber un escritor activo | 1 |
| INVALID_MARKER | El marcador observado no cumple su formato canónico | 1 |
| CONTENT_MISMATCH | Faltan, sobran o difieren archivos declarados | 1 |
| COMMIT_CLEANUP_PENDING | Payload correcto y los dos nombres del marcador coinciden | 1 |
| PENDING_MARKER_CONFLICT | El marcador pendiente contradice al publicado | 1 |
| BUNDLE_BYTES_COMPLETE | Inventario y hashes estructuralmente correctos | 0 |
| RECOVERY_REJECTED | Entrada insegura, cambiante, fuera de presupuesto o error de E/S | 2 |

Ninguno de estos estados aprueba la semántica de un hallazgo, una ejecución,
QA o una firma. Un expediente vacío tampoco permite adivinar qué archivos faltan.
El inspector solo admite directorios planos externos al checkout: hasta 128
archivos regulares, 2,000,000 bytes por archivo y 32 MiB totales. Rechaza symlinks,
FIFO y carpetas anidadas. Dos lecturas estables no prueban que el escritor esté
inactivo ni descartan cambios transitorios restaurados entre observaciones.

## Salvamento y verificación

```bash
python3 -B -m superhunter inspect-local-bundle --source /ruta/entrada
python3 -B -m superhunter preserve-local-bundle \
  --source /ruta/entrada --out /ruta/salvamento-nuevo \
  --source-digest SHA256_DEL_SNAPSHOT_VIGENTE --input-anchor ANCLA_DE_INSPECCION
python3 -B -m superhunter verify-preserved-bundle \
  --source /ruta/entrada --bundle /ruta/salvamento-nuevo \
  --source-digest SHA256_DEL_SNAPSHOT_VIGENTE --input-anchor ANCLA_DE_INSPECCION \
  --recovery-anchor ANCLA_EXTERNA_DEL_SALVAMENTO
```

Las mayúsculas representan argumentos reales obligatorios. El digest del código
es SHA256 de `canonical(quality.source_snapshot())`. La inspección devuelve un
ancla del inventario de entrada; el salvamento devuelve el ancla de su COMPLETE.
Conservarlas por separado para verificar posteriormente.

Cada archivo de entrada, incluido su marcador si existe, se conserva como
`observed-NNN.bin`. El JSON privado registra nombre original, tamaño y SHA256.
El reporte legible y la consola omiten nombres y contenido del original.
El COMPLETE del salvamento significa únicamente que se escribió ese paquete;
no completa la entrada. El original jamás se altera ni se reanuda.

La verificación necesita la entrada y el salvamento, regenera clasificación,
mapeo y reporte, compara cada byte y vuelve a revisar fuentes/evidencia al final.
Si una revisión posterior a la escritura detecta cambios, la operación rechaza;
puede conservarse la salida para examen, sin atribuirle éxito ni borrarla.
Las anclas no autentican al productor. Conservar bytes no reconstruye datos
que el proceso nunca llegó a escribir.

## Validación y límites de alcance

119 focales iniciales PASS y ampliación focal de 195 pruebas con salida 0.
2,992 QA PASS, incluidas 36 nuevas: preflight, colisión sin sobrescritura,
sincronización, cuatro SIGKILL reales, clasificaciones, preservación del original,
rechazo de cambios y promociones, y CLI con códigos no cero para incompletos.
La suite completa y aceptación del commit exacto se documentan en CONTINUATION.md
y `SUPERHUNTER_RECUPERACION_ESCRITURA_20261108.zip`.

M1 continúa parcial y el indicador global sigue en 1/6 hitos cerrados. No se
añade una herramienta de exploración remota, un objetivo o un permiso de operación.
Se reejecutó únicamente el perfil fijo de efectos enteros propios de Geth:
3 constructores y 18 llamadas, más replay nativo en un proceso separado.
La captura antigua se conserva; dos suites cambian solamente su ruta al fixture
versionado nuevo. No se reejecutan Slither/EELS ni otros perfiles Geth, ni se
recertifica NQC. El
verificador histórico conserva su bloqueo preexistente por la raíz ampliada;
la frontera complementaria protege los 642 archivos históricos.

La primera QA quedó bloqueada por el fixture viejo: 1 fallo, 22 errores y 40
pruebas no ejecutadas. Sus recibos se conservan. El primer wrapper nativo
falló al imponer 2 GiB donde el worker original exige poder fijar 4 GiB.
Se corrigió el wrapper; no cambiaron límites de workers ni expectativas de tests.

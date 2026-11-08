# Exportación minimizada de revisiones verificadas

Estado de esta entrega: implementado y probado localmente; publicación remota
pendiente. Es una continuación de la protección de logs y reportes, no un
motor de descubrimiento o explotación.

## Problema que resuelve

El paquete de `review` conserva la evidencia original de QA, laboratorio y
fuzzing. Esto permite verificarla, pero no convierte el paquete completo en
material apropiado para compartir. `share-review` crea otro paquete que omite
los originales y conserva únicamente campos expresamente admitidos.

Flujo conectado:

```text
QA + laboratorio DIABLO/NQC + fuzzing numérico
                     |
              review privado
                     |
       captura cerrada y verificación completa
                     |
       selección de campos + filtrado de texto
                     |
      resumen JSON + Markdown + HTML estático
```

`sharing` está registrado en el control de calidad. Depende de `review` y
`privacy`; la entrada CLI depende de `sharing`. Sus comprobaciones de omisión
de evidencia privada y cambios de fuente son obligatorias para aprobar QA.

## Uso desde la raíz del repositorio

Se necesita una revisión privada válida generada con la versión actual del
código. Se rechazan las evidencias de QA cuyo snapshot esté desactualizado.

```bash
python3 -m superhunter share-review \
  --review /ruta/privada/review \
  --out /ruta/privada/resumen-nuevo

# Solo comprueba consistencia del derivado, no su correspondencia con la fuente.
python3 -m superhunter verify-shared \
  --bundle /ruta/privada/resumen-nuevo

# Vuelve a verificar la fuente y regenera la proyección para compararlas.
python3 -m superhunter verify-shared \
  --bundle /ruta/privada/resumen-nuevo \
  --review /ruta/privada/review
```

No se publican ni envían archivos automáticamente. Las carpetas de salida deben
ser nuevas, estar fuera del checkout y no estar anidadas en la fuente. Se
mantienen permisos 0700 para el directorio y 0600 para cada archivo.

## Qué sale y qué no sale

La exportación contiene exactamente `summary.json`, `SUMMARY.md`, `index.html`,
`export.json` y el manifiesto `COMPLETE.json`. El resumen conserva los 27 hitos
originales y los 50 IDs de capacidades, con sus estados y límites. Incluye
conteos de pruebas y casos sintéticos e identidad del código.

No copia logs, trazas, resultados individuales, fuentes de PoCs, valores de los
casos numéricos ni nombres de pruebas internas. Un marcador de prueba sin
etiqueta colocado en un log privado permanece en el original, pero no llega al
resumen porque el log completo está excluido de la proyección.

El texto de los campos permitidos pasa por `privacy.redact_record`. Esto es
filtrado por reglas finitas. Los textos no etiquetados u ofuscados pueden
contener información que las reglas no reconocen; la revisión humana sigue
siendo obligatoria. La omisión de logs no garantiza que todo campo permitido
sea inocuo. El HTML es estático, sin scripts ni recursos externos; el texto se
escapa para no interpretarlo como marcado activo.

## Qué se comprueba

Antes de exportar se capturan exactamente los archivos del manifiesto privado;
se verifican tamaño, tipo de archivo y hashes; y se ejecutan los verificadores
existentes de QA, laboratorio, grafo causal y fuzzing sobre esos mismos bytes.
Se contrastan nuevamente la fuente y el snapshot del código antes de escribir.
Los archivos originales nunca se reescriben.

Se rechazan archivos extra, manifiestos incoherentes, symlinks, datos demasiado
grandes, campos inesperados, valores de control, conteos con tipos incorrectos,
pretensiones de certificación y reportes que no corresponden a sus datos. La
captura limita cada archivo mediante `safe_io` y el paquete a 32 MB.

Los hashes prueban integridad y correspondencia, no quién produjo los datos.
Un operador capaz de cambiar todos los archivos y hashes puede construir otro
paquete internamente coherente. Por eso existen dos resultados distintos:

| Resultado | Significado |
| --- | --- |
| `SHARED_REVIEW_CREATED` | Se comprobó la fuente y se generó una copia minimizada. |
| `SHARED_REVIEW_CONSISTENT` | El derivado es internamente coherente; la fuente privada no fue comprobada. |
| `SHARED_REVIEW_SOURCE_MATCH` | Se volvió a verificar la fuente privada y coincide la proyección completa. |
| `SHARED_REVIEW_ERROR` | Entrada, fuente, salida o comprobación inválida. |

`producer_authenticated`, `vulnerability_confirmed` y `production_certified`
permanecen en false. `manual_review_required` permanece en true.
`source_reverified=true` no es una firma del productor ni una repetición de las
pruebas originales: es una nueva comprobación de sus artefactos y cálculos.

El metadato de procedencia vincula el manifiesto completo de la fuente; no
incluye hashes individuales de secretos. El derivado está ligado a esta versión
del código de proyección y filtrado. Un cambio de política exige otra revisión,
no cambiar manualmente un hash para forzar aceptación.

## Validación y límites del incremento

La base actual de GitHub se reprodujo con 251 tests. Al reconciliar el parche de
privacidad anterior pasaron 287. Se añadieron 41 pruebas específicas de esta
exportación y la suite completa pasó 328 tests sin omisiones. Los logs finales,
recibos y comprobación del parche acompañan esta entrega.

Las pruebas unitarias de los reportes usan recibos de QA sintéticos, marcados
como fixtures; el control de release ejecuta aparte toda la suite real. No se
cuentan recibos inventados como pruebas ejecutadas. Tampoco se cuentan estas
pruebas como validación de vulnerabilidades externas.

No se ejecutan RPC, contratos Solidity, forks, ataques, envíos a programas de
recompensa ni lectura de credenciales de servicios. No hay certificación global
de seguridad. Los puntos 29 y 47 del catálogo siguen siendo parciales.

## Compatibilidad de la continuación

El esquema de exportación actual es `superhunter-minimized-review-v2`.
Conserva `bounded`, `partial` y `pending` en los 27 hitos. No se convierte un
hito parcial a pendiente ni se lo marca completo durante la exportación.
Los exports v1 deben regenerarse desde el paquete privado original; no cambiar
sus hashes manualmente. El verificador siempre exige su propia política actual.

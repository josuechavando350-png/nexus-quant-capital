# Contraste de diagnóstico y cómputo restringido

El diagnóstico propio produce dos findings operativos con sus planes a partir
de cinco ensayos completos. El perfil restringido ejecuta esos mismos controles
de integridad en otro worker. Este consumidor enlaza los dos expedientes y
comprueba qué evidencia corresponde a cada finding existente.

No ejecuta workers ni reparaciones. Requiere los expedientes originales y el
código exacto de sus productores, ambos con el mismo digest de fuente.

```bash
python -B -m superhunter corroborate-owned-restricted-diagnosis \
  --diagnosis-bundle DIAGNOSTICO --restricted-bundle RESTRINGIDO \
  --source-digest DIGEST --diagnosis-anchor ANCLA_DIAGNOSTICO \
  --restricted-anchor ANCLA_RESTRINGIDO --out SALIDA_NUEVA
python -B -m superhunter verify-owned-restricted-corroboration \
  --diagnosis-bundle DIAGNOSTICO --restricted-bundle RESTRINGIDO \
  --source-digest DIGEST --diagnosis-anchor ANCLA_DIAGNOSTICO \
  --restricted-anchor ANCLA_RESTRINGIDO --bundle SALIDA_NUEVA \
  --corroboration-anchor ANCLA_CONTRASTE
```

Las rutas deben ser disjuntas y estar fuera del código. El directorio de salida
debe ser nuevo. El expediente contiene únicamente inputs.json, comparison.json,
REVIEW.md y COMPLETE.json. La revisión reconstruye el resultado desde ambos
originales; no acepta un informe solo porque sus hashes sean coherentes.

## Condiciones del contraste

Primero se revalidan los dos perfiles completos, sus anclas y la fuente. Se
exigen IDs de experimento y workers distintos, además de inventarios de fuente
iguales. Estas condiciones evitan confundir el mismo expediente con dos perfiles;
no autentican una ejecución ni demuestran independencia de host.

| Ensayo | Comparación adicional |
| --- | --- |
| Baseline y las dos restauraciones | Bytes de resultado idénticos, inventarios, delta y retorno iguales |
| Archivo fijo ausente | Motivo HISTORICAL_TREE_CHANGED y etiqueta exacta de cada perfil, más inventarios, delta y retorno iguales |
| Modo del archivo fijo cambiado | La misma regla cerrada de fallo, conservando la evidencia de modo |

El diagnóstico histórico usa OWNED_BOUNDARY_TRIAL_REJECTED y el worker
restringido usa REPOSITORY_BOUNDARY_BLOCKED. No se reescriben esos bytes ni se
afirma igualdad de las etiquetas. Una etiqueta arbitraria con el mismo motivo
se rechaza. El informe conserva ambos estados, hashes de stdout, igualdad de
bytes y regla aplicada a cada par.

Solo cinco pares completos, los dos perfiles aceptados y todas las comparaciones
coincidentes producen OWNED_CORROBORATION_MATCH. Se enlazan los hashes de los
dos findings y planes existentes con los pares que los respaldan. No se suman
como nuevos hallazgos. Un productor inconcluso conserva INCONCLUSIVE y cero
referencias corroboradas. Un expediente alterado o una identidad incorrecta se
rechazan. CLI: retorno 0 para coincidencia completa, 1 para inconcluso y 2 para
rechazo; los diagnósticos de error no exponen rutas privadas.

Se vuelven a leer los originales y la fuente al terminar. Una mutación durante
la comparación impide publicar el resultado. El verificador comprueba también
que el expediente de contraste no haya cambiado durante su lectura.

## Alcance de la evidencia

Los intervalos monotónicos se conservan y se describe su relación declarada.
No autentican el dominio del reloj ni causalidad o independencia de ejecución.
El hash de la prueba del filtro enlaza la salida ya validada; el consumidor no
vuelve a instalar ese filtro. La adquisición de archivos del worker restringido
sigue ocurriendo antes del filtro.

Los dos fallos son intervenciones declaradas sobre una copia propia, no
vulnerabilidades originales. No se acredita sandbox general, estado actual de
otro destino, aprobación humana, operación continua o reparación realizada.
M1 sigue parcial. La aceptación y su digest se registran en CONTINUATION.md.

Las regresiones incluyen diez ensayos reales entre los dos productores,
descriptor adicional real que vuelve inconcluso al restringido, corrupción y
resellado de informes, IDs repetidos, cambio de contexto, originales modificados
durante lectura, rutas superpuestas y comprobación en otro proceso. El control
de diagnóstico truncado es una transformación declarada de evidencia, no una
interrupción natural. La revisión no inicia procesos nuevos.

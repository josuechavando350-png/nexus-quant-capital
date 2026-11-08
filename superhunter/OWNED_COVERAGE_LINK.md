# Vínculo verificable de los dos expedientes de cobertura

Continuación del PR #86, commit `2ce05781977ad0036c19e78b9b17bee2c04a0bf2`.
El perfil `owned-temporal-coverage-linked-evidence-v1` consume únicamente el
informe histórico de cobertura y el corpus adicional v1. Regenera ambos con
sus verificadores reales antes de construir un resumen común. No ejecuta
detectores, modelos de autorización, compiladores o EVM.

## Identidad de las entradas

El llamador debe proporcionar el digest esperado de código y dos anclas
SHA-256 externas, una por cada `COMPLETE.json`. El comando no toma esas anclas
del informe de vínculo ni sustituye una ausente por un hash calculado allí.
Los valores deben ser distintos y tener el formato SHA-256 exacto.

El digest de código debe coincidir con el checkout y con ambos expedientes.
Los dos directorios de entrada deben ser distintos y no estar anidados. La
salida debe estar fuera del repositorio y de las entradas, en una ruta nueva.
Los inventarios son cerrados: archivos adicionales, faltantes o enlaces
simbólicos en la raíz/archivos de los expedientes se rechazan.

El consumidor captura todos los bytes antes de la revisión, comprueba los
marcadores contra las anclas, ejecuta ambos verificadores y exige que fuentes,
inventarios y bytes permanezcan iguales al terminar. El verificador del
vínculo vuelve a efectuar este recorrido y exige el resumen exacto; recalcular
los hashes de un resumen editado no sustituye las entradas verificadas.

Los hashes seleccionan contenido, **no autentican al productor**. Ambos
algoritmos y sus expectativas comparten especificación y autor. No se prueba
aislamiento de host, independencia de productores o generalización.

## Qué muestra el resumen

| Registro separado | Casos | Secuencias distintas | Condiciones ausentes |
| --- | ---: | ---: | --- |
| Histórico | 11 | 9 | `use_without_control` |
| Adicional | 16 | 13 | Ninguna de las ocho declaradas |

`link.json` enumera los duplicados de cada grupo, los cuatro grupos de
secuencias compartidas y los testigos adicionales correspondientes a condiciones
ausentes en el histórico. Para `use_without_control`, el testigo adicional es
el índice 0 de `use_without_control--present`.

El hueco del corpus histórico sigue visible. Los denominadores no se suman;
un testigo adicional de entrada no demuestra haber detectado el defecto
histórico `latent_revocation`. Esta ruta no recalcula ni reemplaza las métricas
de detección nativas. No calcula porcentaje global de avance.

## CLI

Desde el checkout, tras crear los dos expedientes para este mismo digest:

```sh
python3 -B -m superhunter link-owned-coverage \
  --historical /ruta/privada/historico \
  --additional /ruta/privada/adicional \
  --expected-source DIGEST_ESPERADO \
  --historical-anchor SHA256_COMPLETE_HISTORICO \
  --additional-anchor SHA256_COMPLETE_ADICIONAL \
  --out /ruta/privada/vinculo

python3 -B -m superhunter verify-owned-coverage-link \
  --historical /ruta/privada/historico \
  --additional /ruta/privada/adicional \
  --expected-source DIGEST_ESPERADO \
  --historical-anchor SHA256_COMPLETE_HISTORICO \
  --additional-anchor SHA256_COMPLETE_ADICIONAL \
  --bundle /ruta/privada/vinculo
```

El nuevo bundle contiene `link.json`, `REVIEW.md` y `COMPLETE.json`. Las rutas
locales no se guardan en el resumen. Hay que conservar también los dos
expedientes de entrada y sus anclas para verificarlo posteriormente.

## Validación

32 regresiones focalizadas PASS. Incluyen los verificadores reales y CLI en
procesos separados; no se sustituyen por mocks para el recorrido completo.
Los dobles puntuales solo introducen cambios durante una etapa para verificar
que se rechacen antes de aceptar el resultado.

Se prueban anclas incorrectas/iguales, perfiles intercambiados, versiones
mezcladas, entradas duplicadas o anidadas, inventarios excesivos, symlinks,
mutaciones durante el replay, borrado del hueco histórico, invención de una
detección y modificación del resumen con hashes recalculados.

La validación integral y las aceptaciones nativas de cada digest se documentan
en `CONTINUATION.md`. Los resultados de PR #86 no se atribuyen automáticamente
al nuevo código por conservar sus casos y dependencias.

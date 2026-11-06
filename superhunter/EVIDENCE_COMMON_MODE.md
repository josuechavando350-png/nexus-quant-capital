# SUPERHUNTER — Auditoría de dependencia de un mismo respaldo

**Incremento real y acotado, completamente offline.** Complementa la ablación de evidencia y auditoría dirigida de hipótesis. No detecta ni explota automáticamente vulnerabilidades.

## Problema que resuelve

Dos identidades locales de evidencia pueden apuntar al **mismo paquete original**, lo cual crea redundancia aparente: retirar `sourcea` no rompe el caso porque `sourceb` refiere los mismos bytes; retirar `sourceb` tampoco. Un evaluador ingenuo trataría esos IDs como pruebas independientes.

## Implementación y verificador

- Revalida primero la ablación anterior, su auditoría, el triaje, los originales forenses/EVM y sus recibos por los verificadores existentes.
- Agrupa fuentes por igualdad exacta de SHA-256 de los bytes del `COMPLETE.json` verificado, sin deducir identidades de productores. Distingue la cantidad de IDs declarados de paquetes materialmente diferentes.
- Para cada grupo de alias de bytes idénticos, elimina **virtualmente todos los IDs** al mismo tiempo y recalcula el triaje contra los originales. Señala candidatos donde cada ablación individual parecía resiliente pero la pérdida del respaldo común produce brechas.
- Guarda los resultados en un directorio privado con recibos vinculados a código, prueba y fuentes; `verify-common-evidence` rehace el cálculo en un segundo proceso y rechaza alteraciones y cambios de fuentes, incluso con `COMPLETE.json` recalculado.

## Límites

**Igualdad de bytes no prueba igualdad de productor; diferencias de bytes tampoco prueban independencia.** Un adversario podría producir dos paquetes distintos. Se requiere identidad del productor y custodia verificadas de manera independiente. La ablation es virtual: no ejecuta un exploit, no contacta objetivos, no demuestra causalidad ni confirma vulnerabilidades.

## Ejecución

```sh
python3 -m superhunter audit-common-evidence \
  --ablation /privado/ablation --path-audit /privado/path-audit \
  --triage /privado/triage --sources /privado/sources.json \
  --out /privado/resultado-nuevo

python3 -m superhunter verify-common-evidence \
  --bundle /privado/resultado-nuevo \
  --ablation /privado/ablation --path-audit /privado/path-audit \
  --triage /privado/triage --sources /privado/sources.json
```

Los expedientes resultantes contienen identificadores privados y hashes. No publicarlos en GitHub. En la documentación pública solo describir los resultados agregados y pruebas, no rutas o datos originales.

## Gate

Pruebas con dos IDs que comparten un respaldo, falsa redundancia identificada, un respaldo externo independiente, controles negativos y re-sellado fraudulento, replay en dos procesos, suite completa previa sin omisiones, sin introducir funciones vacías ni dependencias de red. Sin ejecutar herramientas EVM nativas ni certificar NQC.

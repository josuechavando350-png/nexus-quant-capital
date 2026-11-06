# SUPERHUNTER — cortes mínimos de disponibilidad de evidencia

## Problema formal

Para cada hipótesis validada por las herramientas offline anteriores, las observaciones y aristas tienen conjuntos de respaldos que las sustentan. Cada respaldo se identifica por SHA-256 del `COMPLETE.json` previamente verificado. Dos IDs de fuente con **idénticos bytes** cuentan como un solo respaldo a efectos de disponibilidad. Una obligación previamente sustentada pierde cobertura cuando desaparecen **todos** los respaldos que la sostenían.

El motor calcula **todos los conjuntos de fallos mínimos por inclusión** que originan al menos una nueva obligación sin respaldo. El algoritmo elimina supersets, calcula su tamaño y recalcula el puntaje local mediante `critical_chain.validate_and_score` sobre el escenario contrafactual (sin modificar originales). Un test independiente enumera exhaustivamente los subconjuntos de hasta ocho respaldos y compara los cortes mínimos.

**Estos son cortes de disponibilidad de evidencia, no caminos de ataque, no proof-of-exploit, no estimación probabilística ni un indicador CVSS.** Una cadena con impacto crítico declarado no se convierte en crítica confirmada por este análisis.

## Dependencias probadas

`verify-evidence-cuts` invoca `evidence_common_mode.verify`, que reejecuta los verificadores de ablación, auditoría dirigida, triaje y originales forenses/EVM. Los bytes y versiones se verifican nuevamente. Las salidas con originales o identificadores privados permanecen **fuera de GitHub**.

## Uso offline

```sh
python3 -m superhunter audit-evidence-cuts \
  --common /privado/common --ablation /privado/ablation \
  --path-audit /privado/path --triage /privado/triage \
  --sources /privado/mapa.json --out /privado/cuts-nuevo

python3 -m superhunter verify-evidence-cuts \
  --bundle /privado/cuts-nuevo \
  --common /privado/common --ablation /privado/ablation \
  --path-audit /privado/path --triage /privado/triage \
  --sources /privado/mapa.json
```

No hay contactos externos, ejecución EVM nativa, permiso para probar terceros ni prueba de vulnerabilidad. Un SHA-256 autentica **bytes verificados en el expediente**, no al productor. Si la evidencia upstream cambia, el verificador rechaza la entrega.

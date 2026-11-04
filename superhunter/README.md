# SUPERHUNTER — fase 1 (puente de contratos)

Este directorio vive **solo en `nexus-quant-capital`**, sin modificar código histórico de NQC ni el repositorio de DIABLO. La transferencia es mediante archivos JSON tipados y evidencias locales. No hay importación de código de DIABLO, transacciones en cadena, RPC de producción, firma, secretos ni workflows nuevos.

## Contratos

1. `Candidate`: DIABLO propone sospechoso `unverified`, identidad de código y objetivo, invariante, PoC y SHA256 del stdout real de Forge. No asigna severidad final.
2. `Reconstruction`: NQC asocia candidato, bloque+hash, modelo de protocolo, fondos expuestos, costo estimado, beneficio neto, reproducibilidad, confianza y severidad económica propuesta.
3. `Finding`: combinación **aplanada** de ambos contratos más `scope_pass`, `dup_check`, `forge_pass`, `final_severity` y `report_md`, **solo** si pasan todas las puertas.

Los ejemplos del usuario se preservan en estos contratos. Se exige una entrada `admission.json` adicional con evidencia y revisiones independientes para no confiar en los booleanos autocontenidos de un sospechoso:

- `scope`: política aprobada por operador, repo+commit exactos, contratos permitidos/excluidos, fuente y hash de reglas.
- `forge`: manifiesto del test, stdout SHA256 verificado, éxito, identidad del objetivo, fork y enlace afirmado al contrato.
- `nqc`: evidencia JSON de reconstrucción, SHA256, estado y datos económicos ligados al candidato.
- `duplicate`: revisión de auditorías/avisos, `result=none`, fuentes y revisor.
- `severity`: límite por reglas del programa y nivel de impacto revisado.

`prelim_severity=unverified` es un **estado**, no un grado ordinal. Por ello no puede computarse literalmente `min(prelim,economic)`; la severidad final es el mínimo de `economic_severity`, el máximo del programa y el impacto verificado por un revisor. En esta fase se trata de calificaciones de un manifiesto externo, no de un cálculo autónomo.

## Ejecución local

Requiere Python 3.11 o posterior, solo librería estándar.

```bash
python3 -m unittest discover -s superhunter/tests -v
python3 -m superhunter candidate.json reconstruction.json admission.json \
  --evidence-root /directorio/con/forge.log/y/nqc.json --out /directorio/privado/reportes
```

El comando retorna `0` si se genera borrador, `1` si una puerta se rechaza y `2` ante datos inválidos. Siempre escribe `decision.json` si el esquema de entrada era válido; **nunca** produce `report.md` cuando se rechaza.

## Límites conocidos y siguiente etapa

Este es un **puente offline de contratos y verificaciones estructurales**, no un motor autónomo. La validez del `scope` depende de la revisión humana de reglas vigentes. `target_bound=true`, `run_ok=true` y el manifest NQC son **atestaciones externas**, no pruebas de que el código realmente ejecutó contra el objetivo. Un hash demuestra integridad de bytes, no su verdad. Antes de usar este sistema para afirmar hallazgos reales, construir productores verificables que:

- ejecuten el `forge` exactamente en el commit del objetivo, inspeccionen direcciones y generen metadatos del ejecutor de forma independiente;
- reconstruyan estado y resultados económicos directamente mediante NQC y verifiquen diferencias de balance con un motor independiente;
- protejan las evidencias y reportes no divulgados fuera del repositorio público;
- cotejen las reglas actuales de cada programa en su canal oficial.

Los tests incluidos usan fixtures sintéticos. Un `REPORT_READY` significa **borrador apto para revisión**, no explotación validada de un contrato de producción, certificación ni derecho a recompensa.

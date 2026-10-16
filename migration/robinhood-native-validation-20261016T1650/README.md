# NQC: integración de validación nativa

Integra la corrección preparada en PR24 para conservar ecrecover nativo al cargar
el estado histórico. Reutiliza contratos, firma pública, runtime y collector
oficial fijados. Añade un control de firma inválida y preserva seis resultados
ordenados bajo un protocolo publicado antes de medir.

Leer [PROTOCOL.md](PROTOCOL.md). El resultado de la captura será `CAPTURE.md`;
el relevo posterior será `CONTINUITY.md`. El piloto previo fallido permanece intacto.
No se ejecuta bundler completo ni se demuestra financiación/rentabilidad por pasar
validación EVM. Primer incremento del presupuesto de dos aceptado por Chavando.

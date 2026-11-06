# Resultado verificado — NQC Defense 0.2.0

- 100 pruebas del motor y 9 de aislamiento aprobadas; cero fallos o pruebas omitidas en esas suites.
- 3 componentes añadidos: recibos reproducibles, límite transaccional de cuarentenas y vigencia de observaciones locales.
- Verificador independiente de exportaciones con HMAC, política fijada, checkpoint y reproducción de decisiones.
- Fallo del reloj corregido y comparado contra la versión 0.1.0 con bloqueo SQLite real y reloj controlado.
- Revisión completa de NQC recuperada: 645 archivos validados por blob Git. Aislamiento aprobado con las adiciones nuevas.
- Inspección de bytes reales de `nqc-census/Cargo.toml`, recibo reproducido y exportación verificada; archivo sin modificaciones.
- Las únicas adiciones del checkout son `migration/defense/` y `migration/DEFENSE-INTEGRATION.md`. Ningún archivo previamente rastreado cambió.

Hay 8 subconjuntos ejecutables del catálogo original y 5 componentes adicionales ejecutables. No son 100 programas completos. La conexión obligatoria con un consumidor productivo de NQC, los sensores continuos, el hardware especializado y el anclaje externo de auditoría siguen pendientes. No se publicó ni activó nada.

Consultar `VALIDACION.json`, los registros de pruebas, `V0_2.md` y `CONTINUIDAD.md` para continuar desde este estado.

# Sovereign Radar Omega — Fase 0 (solo diseño y prevalidación offline)

**Estado:** integración inicial de arquitectura, **no** un motor operando ni un
certificado de mercado. Entrada: `NQC_Sovereign_Radar_Omega.pdf`, v1.0 del
2026-10-22, SHA-256 `5c1739799ab5099bc95f7347aeed8bcc2e3b098e64c3688584331004f15edf0f`.
Este directorio es nuevo y no reescribe ningún byte PFT/Census importado.

## Inventario verificable

`architecture_v3.json` transcribe las 36 capacidades, su capa y fase del
catálogo (PDF pp. 5–7) y el orden de construcción (p. 9).
La fase 0 comprende IDs **1, 6, 7, 8, 10, 24, 25, 29, 32** (9 de 36).
Todo componente aparece con `omega_verification: not_assessed` porque una
coincidencia de nombre con el código preexistente no demuestra paridad,
completitud, rentabilidad ni pertenencia al nuevo alcance.

`audit.py` verifica que el catálogo no se recorte, que cada componente tenga ID
único y capa, que las fases tengan el recuento correcto, que los criterios de
salida mínimos permanezcan y que el observador no obtenga permisos de gasto.
Es un **control estructural**, no una auditoría de contratos, cadenas,
datos en vivo, ni ejecución económica.

Ejecutar desde este directorio (solo biblioteca estándar):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s . -p 'test_audit.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 audit.py
```

## Próximas puertas técnicas — NO aprobadas todavía

1. Mapear por ID los módulos actuales de `nqc-census/` y `ci/nqc-census/` con su
   alcance/certificación auténtica, sin reetiquetar las autoridades históricas.
2. Certificar verdad de bloque con reconstrucción independiente, lectura directa
   y reproducción EVM; bloquear toda discrepancia de cadena, bloque, contrato,
   versión, parámetros u oráculo.
3. Reconciliar **todas** las posiciones del alcance explícito, no extrapolar a
   mercados no observados.
4. Construir el ledger competitivo histórico con bono, ganador, bloque desde
   oráculo y propina al builder; medir margen después de **todos** los costos y
   cuantificar los casos perdidos o censurados.
5. Someter los resultados al Evidence Vault y a una auditoría independiente;
   si no queda margen probado, congelar el avance a Shadow.

## Límites operativos obligatorios

El observador **nunca** firma, transmite ni gasta. Ninguna API, llave, nodo,
workflow o cuenta se activa por este cambio. Census y Shadow no conectan
fondos. El techo de Canary del plano es **$2,000 MXN**, recarga máxima de
**$500 MXN** y revisión obligatoria tras **$1,000 MXN** gastados sin captura;
ninguno de esos montos constituye una autorización para gastar. Se mantienen
las restricciones de `AGENTS.md` y `migration/IMPORT-PLAN.md`, incluyendo la
prohibición de habilitar workflows heredados y de reclamar recertificación por
traslado de evidencias.

## Qué significa avance

- **Inventario y contratos de aceptación:** medible con `audit.py`.
- **Componentes Omega verificados:** 0/36 hasta mapear implementación real,
  correr pruebas afectadas y obtener evidencia nueva de su alcance.
- **Fase de mercado cerrada:** ninguna por esta incorporación documental.
- Un PASS estructural no autoriza declarar Census cerrado ni avanzar a Canary.

# SUPERHUNTER — Estado verificable y punto exacto de reanudación
**Corte:** 2026-11-06. **Leer primero:** [SUPERHUNTER_MASTER_PLAN.md](SUPERHUNTER_MASTER_PLAN.md).

## Versión pública actual
- Plan maestro publicado en `main`: commit `c19e7f368e4ffd8535f4a6892e4156ed895321d4`.
- Fuente consolidada pública en **PR #45**: https://github.com/josuechavando350-png/nexus-quant-capital/pull/45
- Rama: `feat/superhunter-full-consolidation-20261106`.
- SHA de commit recuperado: `738511fa90cb7fd2bae5e6f9aec6cc64529bc2b8`, cabeza de PR #45 al crear este documento.
- **214** archivos nuevos bajo `superhunter/` verificados contra manifiesto de 214 Git blob SHA-1; **0** modificaciones a `ci/`, `migration/`, `nqc-census/`.
- `main` aún NO incluye el código de PR #45. El PR sigue en **borrador**, sin fusionar.

## Verificación reproducida del paquete
- ZIP original de Biblioteca: `SUPERHUNTER_holdout_etiquetas_2005.zip`; SHA-256 `c5a3ce77720213a3fa4e19da8faac84a41594b7823e90d2ac246d5119e57267f`.
- Reejecutado `python3 -m superhunter check --out RUTA_PRIVADA_NUEVA`: `LOCAL_QA_PASS`, **2005 tests**.
- `python3 -m superhunter verify-check --bundle RUTA_PRIVADA`: `LOCAL_QA_PASS`, **2005 tests**.
- Identidad de fuente actual comprobada: `205b61fee612c263510c581216010c527d84e51f934d2c1ca9451fbd87ed6ed4`.
- No presupone descubrimiento autónomo, hallazgos originales, 20 programas concurrentes reales ni benchmark ciego.
- Quedan sin certificar la suite histórica completa NQC, Rust Census, el verificador integral de aislamiento y GitHub Actions.

## Catálogos y dirección vigente
- `superhunter/integration-checklist.json`: 27 requisitos originales.
- `superhunter/capabilities.json`: 50 capacidades originales.
- `superhunter/research_initiatives.json`: 25 iniciativas originales.
- Plan maestro agrega 100 propuestas identificadas `SH-01-01` ... `SH-10-10`, más cinco líneas de R&D; ninguna nueva se considera terminada por su nombre.
- Estado informal histórico 40–42% NO revalidado; usar hitos y pruebas, no porcentajes.

## Primer incremento de M1 — Forense offline (PR #46)
- PR dependiente: https://github.com/josuechavando350-png/nexus-quant-capital/pull/46 (borrador, base `feat/superhunter-full-consolidation-20261106`).
- Rama `feat/superhunter-forensic-timeline-20261106`; commit implementado `97240f29cab405ed2524f6e0a1c70a2041e5f25e`.
- Archivos cambiados contra la base consolidada: exactamente **8 archivos bajo `superhunter/`**; ninguna modificación a NQC histórico.
- Dos módulos nuevos: `forensic_timeline.py` (cronología de eventos declarados, incertidumbre y control de contradicciones) y `journal_ingest.py` (parser offline de exportaciones `journalctl -o json`, preservación de bytes, offsets SHA-256 por línea, replay verificable).
- Pruebas nuevas verificadas **por separado**: 17/17 cronología + 19/19 journal. Inventario de fuentes/componentes: 143 archivos, 53 componentes, 0 errores de dependencias/mapas.
- **Pendiente de verificar**: suite completa reejecutada sobre 2,005 anteriores + 36 nuevas; `verify-check`, `review-platform` y `verify-platform`. Un PASS parcial NO autoriza declarar la integración terminada.
- Esta fase NO autentica productores, no prueba causalidad/incidente, no implementa sensores remotos, no analizó RAM/disco/PCAP y no descubre vulnerabilidades. NO completar SH-01 ni M1 por este incremento.
- Siguiente paso: completar QA y verificación; luego integrar dos fuentes independientes verificadas y construir primer experimento causal en entorno propio.

## Próxima acción obligatoria
1. Comprobar HEAD real de `main` y PR #45, inspeccionar diff y preservar sus hashes; no hacer force-push ni fusionar a ciegas.
2. Cerrar M0: revisión de aislamiento y NQC histórico antes de propuesta de merge; verificar códigos y límites.
3. Desarrollar M1 en rama dependiente: **primer flujo forense real con evidencia preservada, cronología, inferencia causal acotada, reproducción en sandbox y verificación independiente**. Los submódulos parciales no completan M1.
4. Registrar resultados exactos, controles negativos, versiones y limitaciones en PR. Si el chat termina, reanudar desde este estado y del plan maestro; no pedir reconstruir conversaciones pasadas.

## Límites invariables
Investigación white/grey hat solo en entornos propios, autorizados o reproducciones offline; sin escaneo/explotación de terceros sin permiso, sin divulgar etiquetas privadas, credenciales, fondos, firmas ni datos personales. No tocar `nexus-engine`, Cano/Vercel, workflows heredados ni NQC histórico.

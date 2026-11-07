# NQC isolation contract

- Keep client applications, TypeScript client engines and deployment configuration out of this repository.
- Never write to `josuechavando350-png/nexus-engine` as part of work here.
- Do not interact with Cano, Vercel, client domains, Git integrations or notification settings.
- Preserve immutable original PFT/Census bytes and source provenance. Never bulk-replace old repository, run, artifact or commit identities.
- Original certification does not automatically apply to a new producer repository or commit.
- Keep legacy workflow definitions disabled. Enabling a new workflow needs a separately reviewed migration and exact new producer identity.
- No live trading, signing, broadcasting, deployment, secrets, new subscriptions or permission expansion is authorized by this source import.
- Use offline tests first. Never patch recovered-source in place to make it compile; apply pinned compatibility overlays only to a fresh build copy.
- Run the isolation verifier and affected Python/Rust tests before proposing a change. Report failed, skipped and unrun checks honestly.

## SuperHunter: portafolio externo de 50 repositorios (2026-11-07)

- Antes de proponer nuevas herramientas o alterar la arquitectura de SuperHunter, leer `superhunter/REPOSITORIES_50.md` y `superhunter/repo_portfolio_50.json`; contienen los 50 repositorios elegidos, por qué se propusieron, su función, interfaz, criterios de aceptación y límites.
- La presencia en el catálogo **NO** autoriza clonar, instalar, ejecutar, desplegar, escanear objetivos externos, utilizar credenciales, generar gastos, enviar transacciones ni fusionar código. El estado es `CATALOGUED_NOT_INTEGRATED` para los 50, hasta PR y pruebas separadas.
- No confundir los 50 terceros con `superhunter/capabilities.json` (50 capacidades internas), `integration-checklist.json` (27) ni `research_initiatives.json` (25). Preservar las identidades y la evidencia histórica.
- Consultar `SUPERHUNTER_STATUS.md` y las PRs vigentes, partir de una cabeza verificada en rama aislada y respetar los límites originales de este archivo. Nunca presentar registro documental como implementación o benchmark aprobado.

- Integración experimental iniciada para el candidato #26: leer `superhunter/OTEL_QA_LAB.md` antes de retomar OpenTelemetry. Instrumenta QA local in-memory; Collector no está instalado y la suite completa de la rama nueva no está certificada. No marcar 1/50 como integración verificada por pasar 8 pruebas focalizadas en un harness sintético.

- Segundo adaptador externo iniciado en rama sucesora del PR #70: \`superhunter/SLITHER_OWNED_LAB.md\`, \`slither_owned_runner.py\`, \`slither_owned_worker.py\`. Solo contiene una ruta fija a un contrato de laboratorio; nunca habilitar objetivos arbitrarios o escaneos de terceros al continuar. La CLI ejecutable aún no cuenta con prueba nativa de Slither ni QA completo en esta rama. No confundir pruebas con subprocess simulado con integración certificada.

- Nuevo control diferencial de Slither (#6): leer `superhunter/SLITHER_PAIR_GATE.md`. Exige detector positivo sobre OWNED con tx.origin y **cero alertas** en versión msg.sender. El par queda INCONCLUSO sin Slither/solc auténticos, sandbox sin red, QA íntegra y replay independientes. No marcarlo integrado en producción por el gate sintético.

- El gate más reciente de Slither #6 ahora exige **tres** fuentes OWNED (positivo, limpio y comparación `tx.origin == msg.sender`); leer `superhunter/SLITHER_THREE_CONTROL_GATE.md`. El PR de este gate es sucesor de #72. Sus resultados reales siguen pendientes: no confundir el modelo del detector con una corrida Slither/solc, ni dos controles negativos con precisión general.

- Conciliación de #73 (tres controles Slither) y #74 (comparación de dos ejecuciones): leer `superhunter/SLITHER_TRIPLE_REPLAY.md`. Los seis reportes se contrastan con `pair.accept` y `check_context` reales; no declarar autenticidad de productores ni independencia de host. Requiere QA y ejecuciones nativas en laboratorio antes de promoción.

- Verificación adicional del comparador Slither: dos expedientes de directorios distintos con **anclas SHA-256 idénticas** deben rechazarse como evidencia duplicada (`DISTINCT_EXTERNAL_ANCHORS_REQUIRED`); revisar `superhunter/SLITHER_TRIPLE_REPLAY.md`. Anclas diferentes no autentican ejecuciones independientes.

- El comparador Slither revalida los hashes **también después** de cotejar los seis reportes. Ver `superhunter/SLITHER_TRIPLE_REPLAY.md`. Una mutación concurrente del manifiesto se rechaza; la consistencia SHA no autentica al productor ni sustituye pruebas con Slither/solc real.

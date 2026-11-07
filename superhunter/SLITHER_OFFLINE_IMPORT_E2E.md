# SuperHunter — Prueba E2E offline del importador real de Slither

**Alcance:** nuevo test `tests/test_slither_offline_endtoend.py`. No ejecuta Slither, solc, objetivos, RPC ni escáneres; sus entradas son **JSON sintético con formato de salida de Slither**. No instala paquetes ni toca NQC histórico.

## Problema que soluciona

Los tests de comparación de los PR #74–#77 sustituyen `slither_control_pair.verify_pair` y `static_review.verify_report` por resultados sintéticos. Esos tests prueban la lógica comparadora, pero **no** que el adaptador real de importación, el registro forense, los manifests anidados y el verificador de contexto funcionen conjuntamente.

El nuevo test E2E genera tres reportes sintéticos **dentro de cada uno de dos paquetes**. En cada caso escribe los bytes exactos de Solidity OWNED, emite un JSON compatible con Slither y un contexto con hash de origen. Importa el reporte mediante `static_review.import_report`, con su `native_runtime` de fuentes ancladas, auditoría real e integridad verificada. Construye los manifiestos de `slither_control_pair`, comprueba ambos paquetes con `pair.verify_pair` y después ejecuta `slither_pair_replay.create` y `verify` reales con dos anclas externas diferentes.

Se incluyen **cuatro métodos**:
- `test_real_offline_import_verification_and_six_report_comparison`: recorrido de extremo a extremo y seis verificaciones sobre dos paquetes reales de evidencias **sintéticas**.
- `test_real_importer_rejects_wrong_source_offsets_before_bundle`: un mapeo de origen imposible no crea salida aprobada.
- `test_real_verifier_rejects_altered_original_source_even_if_content_resealed`: alterar la fuente y recalcular *ambos* manifiestos no elimina el vínculo al hash declarado del código.
- `test_synthetic_report_is_never_claimed_as_native_scanner_proof`: incluso si una entrada sintética **miente** diciendo `input_kind=external-report`, el importador no marca `scanner_execution_verified`, `producer_authenticated`, `repository_commit_verified` ni `vulnerability_confirmed` como verdaderos.

## Límite de autenticidad deliberadamente comprobado

En el laboratorio el informe es fabricado por el propio test, aunque declara la clase `external-report` para ejercer el contrato exigido por el importador del PR #71. Asimismo, el resumen sintético presenta `scanner_executed_in_local_worker=true` únicamente como una **afirmación no autenticada que debe mantenerse sin confirmar**. Los flags de autenticación del informe final permanecen `false`.

No se genera un documento público de hallazgo. La prueba demuestra consistencia y reproducción determinista del procesamiento offline, **no** la ejecución del scanner, independencia de dos hosts ni descubrimiento original.

## Estado y gates pendientes

- **Código escrito y registrado en quality.py:** cuatro casos obligatorios del E2E offline sobre importadores/validadores reales.
- **Validación estructural de GitHub:** verificar nombres, dependencias, componentes y diff de alcance al terminar.
- **Ejecución real de estos tests:** PENDIENTE hasta disponer de checkout completo en Linux/Python 3.12 con los módulos de fuentes históricas y dependencias fijadas; no afirmar 4/4 PASS antes de ejecutar.
- **Ejecución Slither genuina y QA integral:** PENDIENTE. La ruta de laboratorio debe obtener reportes de Slither 0.11.6 y solc fijado, bajo sandbox sin salida a red, con hashes y pruebas independientes antes de poder certificar #6.

**Para futuras IAs:** estos cuatro tests complementan, no sustituyen, los 23 tests de `test_slither_pair_replay.py`. No confundir los 50 repos externos del portafolio con las 50 capacidades internas originales ni presentar el éxito del test offline sintético como bug bounty o eficacia del cazador.

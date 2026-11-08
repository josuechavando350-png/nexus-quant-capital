# SuperHunter — primer adaptador OpenTelemetry para QA

**Referencia:** herramienta #26 del portafolio de 50: https://github.com/open-telemetry/opentelemetry-collector.
**Estado:** ADAPTER_IN_LAB para instrumentación del SDK; Collector NO instalado, conectado ni activado. No se ejecuta escaneo externo, acceso RPC, ni exportación de telemetría. No equivale a una integración en producción.

## Función y por qué se eligió

El QA de SuperHunter ya tiene ocho workers, límites y recibos verificables. Antes de escalar con Ray o NATS necesitamos medir tiempo real de ejecución y distinguir fallos de resultados aprobados. Esta unidad produce spans OpenTelemetry reales para quality.run_check y quality.verify_bundle, solo en memoria mediante SDK 1.42.1. No crea un proveedor global ni configura exportación OTLP. El tiempo medido es observacional, no prueba independiente de autenticidad.

## Instalación opt-in en un checkout aislado

No ejecutada en el repositorio GitHub ni en sistemas del usuario. Comandos orientativos para un operador, después de verificar el origen de las dependencias:

    python3 -m venv /privado/venv-otel
    /privado/venv-otel/bin/python -m pip install -r superhunter/requirements-otel-qa.txt
    /privado/venv-otel/bin/python -m superhunter doctor-otel-qa

Las versiones directas están fijadas, pero el archivo todavía NO incluye hashes de transitivas ni constituye SBOM. En el entorno de pruebas disponible ya estaban instalados OpenTelemetry API/SDK 1.42.1; no se instalaron paquetes en infraestructura del usuario.

## Comandos de ejecución y reproducción

Elegir rutas privadas nuevas fuera del checkout, y no reutilizar paquetes de otro commit:

    /privado/venv-otel/bin/python -m superhunter profile-owned-qa --qa-out /privado/qa-nuevo --telemetry-out /privado/otel-nuevo
    /privado/venv-otel/bin/python -m superhunter verify-owned-qa-profile --bundle /privado/otel-nuevo --qa-bundle /privado/qa-nuevo

El comando de perfil llama al QA REAL y a su verificador; el verificador separado requiere el recibo QA correspondiente para aprobar una telemetría exitosa. El paquete de telemetría contiene telemetry.json, PROFILE.md y COMPLETE.json con hashes SHA-256, sin incluir secretos o mensajes privados de excepción.

## Validación inicial de #70 y pendientes históricos

**Realizada:** 8/8 pruebas focalizadas locales PASS en Python 3.13 con OpenTelemetry SDK 1.42.1, utilizando un QA stub que simula quality.run_check y quality.verify_bundle. Los spans, el exportador solo en memoria y la comprobación de dependencias OpenTelemetry sí se ejecutaron. Se cubrieron fallo de QA, fallo de su verificador, adulteración del manifiesto, rutas de salida y red bloqueada durante los casos de laboratorio.

**NO realizada:** la suite completa de SuperHunter, instalación en su entorno Python 3.12, benchmarking p95 de múltiples ejecuciones, aislamiento estricto de host, ni despliegue de OpenTelemetry Collector.

**Criterios para promover:** (1) QA completo sobre el commit nuevo con cero skips y verificador independiente PASS; (2) entorno Python 3.12 y dependencias fijadas por hashes; (3) mediciones repetibles con p50/p95 y overhead de instrumentación; (4) sólo después, diseño de exportación a Collector con control estricto de datos y permisos.

Para futuras IAs: NO declarar SuperHunter 10/10 o que el proyecto #26 está integrado a producción; registrar este cambio como prototipo de instrumentación real en laboratorio. Los 50 repos externos no sustituyen las 50 capacidades internas históricas.

## Iteración de integridad y QA real

La versión posterior a #79 incorpora pins de ocho dependencias, conserva lectura v1 y ejecuta el perfil v2 con 2,574 tests reales y verificador separado. Consultar [OTEL_DEPENDENCY_INTEGRITY.md](OTEL_DEPENDENCY_INTEGRITY.md) para los hashes, resultados actuales y límites. La medición única no cierra p50/p95, overhead ni integración de Collector.


## Estudio posterior sobre código congelado — 8 de noviembre de 2026

El [estudio pareado de tiempos](OWNED_QA_TIMING_STUDY.md) completa 24 corridas reales sobre PR #90: doce por modalidad, mismas 2,833 pruebas y límites. Se verificaron los 24 expedientes QA y doce de telemetría sin SDK. Aporta medianas y p95 empíricos de esta muestra, con diferencias de ambos signos; no identifica costo causal ni un p95 poblacional fiable. Collector permanece sin integración acreditada. Los resultados históricos anteriores conservan sus propios digests y alcance.

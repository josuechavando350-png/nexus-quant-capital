# Censo por lotes — Morpho Blue / Ethereum

**Recolector implementado y probado offline. Lectura real bloqueada antes de HTTP. Ninguna ganancia demostrada.**

Este módulo elimina la lista manual de uno a tres mercados de NQC067. Solicita globalmente posiciones de mercados listados en Ethereum (chain 1) con healthFactor_lte=1.02, ordenadas por riesgo según el indexador. No es un censo de todo Ethereum: excluye mercados no listados y posiciones fuera del filtro. No autentica salud onchain.

## Implementación

`batch.py` procesa hasta 1,000 registros por página y 10 páginas por ejecución, sin consultas individuales por mercado. Deduplica por mercado y prestatario, agrupa mercados y registra filas inválidas, totales cambiantes, páginas repetidas y cobertura incompleta. Un fin de paginación declarado no demuestra cobertura completa al mismo bloque.

Reutiliza sin modificaciones las funciones de escritura inmutable, fechas y hashes de `../nqc-067-shadow-blue-public-indexer/shadow.py`, comprobando su blob Git. La consulta también está fijada por SHA-256. No hay claves, wallets, RPC, firma, operaciones comerciales ni proceso permanente. Los identificadores detectados quedan pendientes de estado, precio ejecutable, costos y financiación; no reciben una etiqueta de rentabilidad.

El acceso de red requiere `--fetch-approved-once`. El archivo `ACCESS_HOLD.json` lo bloquea en esta entrega. Una ejecución autorizada conserva un bloqueo exclusivo por checkout desde antes de la primera solicitud; no existe opción de ignorarlo ni limpieza automática. Máximo diez solicitudes, separadas al menos dos segundos, con límite de respuesta de 2 MB. No reintenta ni sigue redirecciones. Esta protección es local, no un contador distribuido global.

## Resultado efectivo

Una llamada pública global a la API oficial falló por DNS antes de recibir respuesta HTTP. `CONNECTIVITY.json` conserva el error, fecha y hash de solicitud. El visor web tampoco obtuvo el cuerpo de mercado. No se demuestra una caída de Morpho ni ausencia de oportunidades: no hubo datos recibidos.

Desktop Commander estaba pausado por cuota y no se volvió a llamar ni reconectar. No se habilitaron workflows, servicios, suscripciones, facturación ni fondos. No hay ejecución en segundo plano.

**Capturas reales: 0. Posiciones y mercados reales examinados por este recolector: desconocidos. Beneficio NQC: no demostrado.**

## Validación

Se ejecutaron 28 pruebas nuevas y las 28 pruebas originales de NQC067: 56 aprobadas, cero fallos. La prueba de capacidad usa 10,000 registros sintéticos de 37 mercados sintéticos, distribuidos en diez páginas. Estos números son capacidad de procesamiento probada, no oportunidades observadas. El ZIP entregado en la conversación conserva ambos registros completos de pruebas y la dependencia original.

No se ejecutó el verificador integral PFT/Census, Rust ni las demás suites históricas: no se dispone aquí del checkout completo y sus objetos originales. No se reclama recertificación histórica, replay EVM ni latencia de producción.

## Reproducción sin red

Desde este directorio dentro del repositorio:

```sh
python -m unittest -v test_batch.py
python batch.py --plan
python batch.py --offline-pages /ruta/a/paginas --out /ruta/nueva/a/resultados
```

Las páginas archivadas deben llamarse `page-000.response.json`, `page-001.response.json`, etc. El propietario no necesita ejecutar comandos desde Android.

**Decisión:** se resolvió la limitación de selección manual en el recolector; no se resolvió el acceso real a datos. El próximo paso útil es una ejecución de este mismo módulo en un entorno con conectividad autorizada, tras revisar el bloqueo. No otra estrategia, otro cálculo de P&L sintético ni otra investigación mercado por mercado.

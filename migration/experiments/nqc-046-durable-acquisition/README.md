# NQC046 — comprobar durabilidad fuera del disco temporal

19 de octubre de 2026. Continuación de NQC045 `d066610d23ec5433365f08c46c7f73faec69e526`. Rama única de este trabajo: `research/nqc-046-durable-acquisition-20261019`. Solo archivos nuevos; no se modifica la adquisición previa ni su presupuesto.

## Comprobaciones externas nuevas

El conector GitHub expone `update_ref` con `expected_sha` y `force=false`. Se prepararon dos commits hermanos, con intentos A y B distintos en el mismo archivo de reserva **DRY_RUN**. El primer movimiento de rama desde la base al intento A devolvió éxito. El segundo, conservando la base anterior como expectativa, devolvió `UNKNOWN/GithubGraphQLAPIError`. Se leyó de nuevo la rama: conservaba exactamente A, y los bytes recuperados coincidían con su blob.

La persistencia y lectura por commit quedaron observadas. **La causa del error del segundo movimiento no quedó clasificada**: no se afirma que el ensayo haya demostrado rechazo por lease, exclusión concurrente universal o atomicidad de toda la adquisición. Los intentos se enviaron secuencialmente, no se simuló una carrera real de servidores. No se reintentó ese movimiento, no se forzó la rama ni se hizo una consulta RPC.

`evidence/GITHUB_PROBE.json` conserva las identidades exactas y el error observado. Los commits candidatos A/B comparten el padre NQC045; B quedó como objeto sin avanzar la rama. No se abrió PR ni se modificó main.

Para verificar una recuperación útil, `evidence/checkpoint/SESSION.json` contiene un estado **sintético** NQC040: petición 1 reservada, sin respuesta. Se publica junto con META que declara DRY_RUN. `recover_probe.py` crea un almacén Git nuevo, recupera el commit de prueba desde GitHub sin copiar objetos locales, extrae ese checkpoint y ejecuta el guard original NQC040 con transporte espía. Debe conservar la reserva, devolver `BLOCKED_AMBIGUOUS_ATTEMPT` y realizar **cero llamadas al espía**. La respuesta real de la prueba queda en `evidence/RECOVERY.json`.

Esto vincula la recuperación durable con el comportamiento ya implementado de NQC040. No convierte el prototipo en un adaptador productivo completo: todavía se debe garantizar la reserva remota confirmada antes de cada envío, vincular un único escritor/registro operativo, persistir y revalidar respuestas antes del siguiente paso y detenerse ante cualquier confirmación ambigua. Una restauración de una reserva sin respuesta jamás autoriza reenviarla. No se cambia automáticamente a otra rama ni se inicializa otro presupuesto.

## Bloqueo nuevo observado

Remote Desktop Commander enumeró un dispositivo NQC existente en línea. La siguiente lectura de configuración devolvió que las llamadas estaban pausadas por haberse alcanzado el uso mensual y ordenó no reintentar ni reconectar. No se ejecutó ningún proceso allí, no se consultaron archivos o credenciales, no se reconectó ni contrató capacidad adicional. Esta es una restricción de esa herramienta; no de Triport. No se verificó que ese dispositivo contuviera la clave o pudiera resolver su transferencia.

En el ejecutor actual solo se comprobó la **presencia booleana** de `NQC_TRIPORT_API_KEY` y `NQC_ARCHIVE_RPC`: ambas ausentes. No se buscaron secretos en archivos, historial o sesiones. La transferencia navegador→ejecutor previamente fallida no se repitió. No se volvió a buscar proveedor ni a consumir Blockscout.

## Alcance y reproducción

La prueba de recuperación utiliza GitHub por lectura; las pruebas de NQC040 y aislamiento son offline. No contiene cliente RPC nuevo, ni usa claves reales, ni crea una sesión de adquisición operativa. El fixture de reserva no consume una de las ocho lecturas reales autorizadas. Los dos presupuestos se etiquetan por separado.

```sh
python migration/experiments/nqc-046-durable-acquisition/recover_probe.py --commit COMMIT_DEL_CHECKPOINT
python -m unittest discover -s migration/experiments/nqc-040-resumable-intake -p 'test_*.py' -v
python -m unittest discover -s migration -p test_isolation.py -v
python migration/verify_isolation.py
```

Usar el commit exacto indicado en `evidence/RECOVERY.json`, no la palabra literal del ejemplo. Los checksums de las fuentes previas, resultados efectivos y logs quedan en `SOURCE_BINDING.json`, `VALIDATION.json` y `MANIFEST.json`. No se vuelve a sumar la regresión previa de 140 pruebas; no hubo cambios del algoritmo histórico que justificaran repetirla completa.

Fuentes del contrato de API: descripción del conector GitHub `update_ref` (`expected_sha`, `force=false`) y [API de contenidos de GitHub](https://docs.github.com/en/rest/repos/contents) para el análisis inicial de alternativas. La prueba ejecutada usó commits/ref, no Contents API. La documentación no sustituye el resultado observado del ensayo.

**Estado final: cero consultas Triport autenticadas, cero pruebas históricas de estado, `commercial_admission=false`.** La vía de persistencia tiene una comprobación operativa nueva; el registro productivo y el canal soportado de credencial siguen pendientes. Sin esos requisitos, no existe autorización técnica para disparar el plan aunque el usuario ya haya aprobado sus ocho lecturas. No se necesita una computadora del usuario para reproducir estas comprobaciones.

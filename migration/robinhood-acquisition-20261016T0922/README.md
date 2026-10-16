# Adquisición completa preparada; captura detenida por límite del proveedor

**El proveedor respondió HTTP 429 con `5/second request limit reached`.**
El ensayo se detuvo en la décima petición, sin reintentos, cambio de endpoint o
rotación de rescate. Se conserva un prefijo nuevo de 10,000 bloques, pero **no
comenzó la fase de observación**: cero de doce adquisiciones previstas medidas.
No hay un resultado nuevo de latencia completa, candidatos o rentabilidad.

Código y reglas publicados antes del primer RPC en
[d03ecc8](https://github.com/josuechavando350-png/nexus-quant-capital/commit/d03ecc8e1106488e80d33d8a4beecff65375db80),
sobre PR15 `170148bf07920ae0e9112cc7f28507ca6051dd77`.
Las **46 fuentes registradas** permanecen idénticas. Los protocolos anteriores
no se modificaron para acomodar el resultado.

## Evidencia real del 16/oct/2026

Captura: **09:32:09.516–09:32:14.639 UTC**; 5.123 segundos de journal,
10 métodos RPC/10 HTTP y un error. El proceso terminó con código 1. Se guardaron
14,465 bytes de cuerpos, incluido el cuerpo del rechazo, sin suprimir la parada.

| Resultado | Estado comprobado |
| --- | --- |
| Cola nueva validada | 89,902,198–89,912,197; 10,000 bloques |
| Borrow nuevos / cuentas nuevas del prefijo | 0 / 0 |
| Prefijo acumulado | 88,646,281–89,912,197; 1,265,917 bloques |
| Borrow / cuentas conservadas en el índice | 57 / 30 |
| Objetivo de cola elegido antes del rechazo | 89,973,963 |
| Bloques faltantes hasta ese objetivo histórico | 61,766 |
| Petición rechazada | `eth_getLogs`, 89,912,198–89,922,197 |
| Cohorte congelada / adquisiciones medidas | No / 0 de 12 |
| Cobertura actual de deuda / candidatos actuales | No medidos |
| Rutas, firmas, transacciones, fondos comprometidos | Ninguno |

La respuesta original está en
[`evidence/pilot/010-logs-89912198.json`](evidence/pilot/010-logs-89912198.json):

```json
{"code":-32007,"message":"5/second request limit reached"}
```

SHA-256 del cuerpo: `977657f4ae29177c49f1f5b3c1ef4cd318b13b7372f41d6332d9ec934c27c3c5`.
El ledger conserva status HTTP 429, método, filtro, tiempos, socket y excepción.
Su campo heredado `response_complete=false` indica que el transporte no devolvió
una respuesta RPC exitosa; no afirma que los 58 bytes del cuerpo HTTP estén truncados.

La preparación con conexión reutilizada permitió una ráfaga: las peticiones 3–10
comenzaron dentro de aproximadamente 912 ms según el reloj local. Esto es compatible
con el rechazo por frecuencia. No demuestra la ventana interna, el alcance de la
cuota, ni ausencia de otros consumidores. El mensaje es un límite declarado en
esta respuesta del endpoint demo, **no un contrato de capacidad garantizada**.

## Qué se implementó y verificó

El nuevo runner usa transporte persistente para índice, autenticación, cabecera,
lectura única fijada por hash y comprobación canónica. Conserva la selección de
cuentas por eventos Borrow, nunca por salud o liquidaciones conocidas. Actualiza
solo la cola, conserva cuentas con deuda cero y congela únicamente tras completar
y autenticar el objetivo. Una sola rotación planificada antes de las observaciones
permite distinguir arranque frío; no reinicia tiempo, bytes o contador de métodos.
Esa rotación **no ocurrió en la captura real**, porque el rechazo fue anterior.

La medida planificada comienza antes de la solicitud de cabecera y termina
después de comparar la cabecera canónica posterior. Conserva cabeceras repetidas
como tales y rechaza regresiones/reorgs. No incluye rutas, inclusión ni costes de
gas/Nitro/DA. `PRE_REGISTER.md` define exactamente los relojes y exclusiones.

La auditoría reproduce consultas, orden, journal, archivos persistidos, cohortes,
estado y tiempos sin conexión. La captura real detenida reconstruye exactamente
el registro parcial, sin promoverlo a una cohorte congelada ni inventar muestras.
Los segmentos de la fuente quedan byte a byte conservados en el nuevo prefijo.

**92 pruebas Python aprobadas:** 12 nuevas y 80 de regresión/aislamiento.
Las nuevas inyectan fallos en las **59 peticiones** de un flujo sintético completo;
cubren ambos lados de la rotación, límites compartidos de tiempo/bytes/solicitudes,
errores HTTP/RPC/JSON, reorgs, cabeceras repetidas/regresiones y alteración de archivos
o métricas. Los resultados sintéticos no representan mercados ni ingresos.
377 blobs originales verificados; 106 workflows deshabilitados, cero activos.
Solidity y Rust no cambiaron ni se volvieron a ejecutar.

## Nueva fuente: prefijo válido, objetivo incompleto

Archivo para una continuación posterior autorizada:
`migration/robinhood-acquisition-20261016T0922/evidence/pilot/registry.json`.

- Raíz: `c57a798823c6163a54588353b92269fd98cd050cc96c9afb6123741d6752f7de`.
- SHA-256 del archivo: `67d8a5c619bf025e410e785838e9f08b5919a6e844112eb22911b17369c501ee`.
- Estado: `valid_prefix`, checkpoint 89,912,197. Su validación local no certifica
  que siga siendo canónico: debe revalidarse antes de cualquier continuación.
- La fuente PR14 y su evidencia original siguen intactas. No volver a usarlas
  como punto de partida si ello repite los 10,000 bloques ya validados aquí.

Los resultados de cobertura del PR15 eran históricos. Este ensayo **no volvió
a leer deuda**, por lo que no asigna cobertura vigente ni cuenta de deudores.
Tampoco demuestra que haya o no oportunidades en el mercado actual.

## Siguiente paso, sin repetir tras la denegación

No se harán más consultas RPC en esta ejecución. El siguiente incremento debe
publicar un protocolo nuevo con **control global del ritmo de peticiones**, antes
de continuar desde el prefijo. La misma restricción debe incluir índice, cabeceras,
lectura, autenticación y comprobaciones; no usar conexiones extra para saltarla.
Una propuesta conservadora es separación mínima de 350 ms entre inicios, sujeta
a validación offline, sin ráfagas acumuladas ni reintentos. No afirma admisión del
proveedor y no es una modificación retroactiva de este protocolo, que no tenía
esperas deliberadas. Cualquier nuevo 429 vuelve a detener todo.

Contabilizar las esperas del limitador **desde antes de admitir la cabecera**, no
solo el tiempo de red después de esperar. Tres peticiones por adquisición y una
separación de 350 ms limitan la cadencia sostenida a aproximadamente una adquisición
cada 1.05 s como mínimo; esto puede entrar en conflicto con el objetivo supuesto
de un segundo. Publicar también tiempo en red y cadencia, sin ocultar la cola.
Velocidad de transporte y capacidad admitida son requisitos distintos.

Primero medir adquisición completa bajo un ritmo admisible y cola actualizada.
Después ampliar el pasado pendiente 88,246,281–88,646,280 con política separada.
Solo cuando aparezcan candidatos nuevos, medir supervivencia y ciclo AA/Nitro/DA.
Captura repetible, margen neto, bundler y patrocinio financiado siguen pendientes.

## Reproducción offline

Python 3.12 y dependencias exactas de PR15. Desde la raíz:

```bash
python -m unittest discover -s migration/robinhood-acquisition-20261016T0922 -p 'test_*.py' -v
python migration/robinhood-acquisition-20261016T0922/audit_acquisition.py migration/robinhood-acquisition-20261016T0922/evidence/pilot --out /tmp/nqc-acquisition-audit.json
python migration/verify_isolation.py
python migration/engine-v2-20261015/verify_import.py
```

El comando real y los hashes están en `evidence/provenance.json`;
`MANIFEST.sha256` fija el paquete. `summarize.py` y `build_evidence.py` son reporting
posterior, no intervinieron en la captura. No repetir el runner para sustituir este
resultado negativo. Confianza alta en la parada y el prefijo reconstruido;
**ninguna conclusión nueva de velocidad completa o rentabilidad**. Una fuente RPC,
sin prueba criptográfica independiente de veracidad del proveedor.

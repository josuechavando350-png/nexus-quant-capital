# Detección defensiva de permisos a lo largo de una secuencia

Perfil cerrado: `owned-temporal-authority-v1`. Son modelos Python y registros
abstractos propios; no son credenciales reales, un servicio de autenticación ni
ejecución de contratos EVM. No hay firmas, claves, RPC, objetivos o transacciones.
Los eventos de concesión/revocación representan órdenes locales de control
confiables dentro de este modelo; no se prueba su autenticidad remota.

## Qué se comprueba

El detector recibe exclusivamente eventos y observaciones, sin identificador de
caso, variante del productor o etiqueta de verdad. Reconstruye permisos activos
y generaciones, comprueba vinculación del principal y ámbito, y revisa que una
operación aceptada produzca exactamente un efecto en su contador correspondiente.
Una revocación invalida permisos previos; volver a conceder incrementa la
generación y no rehabilita un registro abstracto antiguo.

La ruta principal mantiene estado incremental. Una referencia separada consulta
los eventos anteriores y reconstruye la decisión esperada por historial. Un
desacuerdo bloquea la evaluación. Ambas rutas comparten especificación y esquema
de entrada: su acuerdo no prueba completitud ni independencia de productores.

El modelo permite repetir una solicitud autorizada con un registro vigente.
No implementa registros de uso único ni pretende demostrar protección contra
repetición en un sistema real. Los cuatro contadores son efectos sintéticos,
sin tokens, dinero o valoración económica.

## Corpus y resultados que debe conservar

Hay once casos conocidos de modelo y secuencia: cuatro controles correctos y
siete casos con defectos sembrados, correspondientes a seis mutaciones distintas.
Seis casos ejercen el defecto; uno deja inactiva la mutación de revocación.

| Política | TP | TN | FP | FN |
|---|---:|---:|---:|---:|
| Completa | 6 | 4 | 0 | 1 |
| Solo decisión, sin efectos | 5 | 4 | 0 | 2 |
| Emisión histórica, sin vigencia temporal | 4 | 2 | 2 | 3 |

Estos valores son una expectativa de regresión del corpus conocido; la aceptación
de una entrega requiere ejecutarlo y conservar los resultados obtenidos. No se
sustituyen mediciones por esta tabla.

La omisión `latent_revocation` permanece como FN frente a la etiqueta del modelo
defectuoso. Su secuencia no revoca permisos y produce exactamente la misma traza
que `clean_repeat`. Este observador no puede distinguir esos dos modelos mediante
esa traza. Un resultado negativo significa ausencia de infracción observada,
nunca prueba de ausencia de defectos. El informe conserva el denominador de siete
casos defectuosos y no oculta el caso no activado.

Las 42 observaciones y repeticiones con tres políticas
no son muestras independientes. No es un benchmark ciego ni prueba de
generalización. Los desarrolladores conocen casos y etiquetas.

## Ejecución y verificación

Desde el checkout publicado, con una carpeta nueva fuera del código:

```bash
python -B -m superhunter evaluate-owned-authority --out /evidencia/temporal
python -B -m superhunter verify-owned-authority --bundle /evidencia/temporal --expected-source SHA256_DEL_CODIGO
```

La verificación se ejecuta en otro proceso para aceptación. Exige el digest del
código revisado, inventario exacto y hashes; vuelve a ejecutar los once modelos
fijos, consulta la referencia, recalcula métricas y compara los artefactos completos.
Cambiar una omisión, etiqueta, traza o afirmación y recalcular el manifiesto no
reemplaza esa repetición. El marcador se vuelve a comprobar byte por byte al
final. Faltantes, extras, enlaces simbólicos y cambios de fuente bloquean.

El código de salida cero indica que la evaluación terminó; las omisiones siguen
en el resultado y `all_seeded_cases_detected` permanece falso. La suite QA prueba
además 1296 secuencias cortas propias y 96 secuencias con varios ámbitos para
comparar las rutas. Son controles de regresión, no casos adicionales del benchmark.

Los catálogos históricos 27/50/25 no se reclasifican por este laboratorio.
Plataforma completa: no. Vulnerabilidades originales confirmadas: ninguna por
esta evaluación. Avance global no determinado.

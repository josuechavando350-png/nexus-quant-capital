# Conciliación económica exacta — alcance y reproducción

Este módulo nuevo de SUPERHUNTER reconcilia dos tablas de balances y una lista
explícita de movimientos. Ejecuta cálculos reales sobre los datos suministrados.
NO reconstruye bloques ni llama EVM/RPC; no calcula dinero robable, beneficios
de un atacante ni severidad de vulnerabilidades. No sustituye Protocol/Fork ni
presenta RMC-016 como un reconstructor que no es.

## Circuito integrado

`reconcile-balances` → validación estricta → cálculo entero y referencia Decimal
→ comparación exacta → bitácora nativa AuditLog de DIABLO → paquete privado.
`verify-balances` recalcula las ecuaciones y comprueba la bitácora, las fuentes,
los originales y el reporte. No depende solo del hash de una salida declarada.

`review-platform` ejecuta además tres controles contables bajo `economics/`,
después del laboratorio y fuzzing numéricos. Esta etapa es obligatoria, se
verifica de nuevo en `verify-platform` y aparece en STATUS.md/index.html.
Si falta o se contradice, no se emite aprobación de la revisión conjunta.
El reporte portátil legacy `publication/` conserva su alcance QA/lab/fuzz;
los originales contables están en `economics/` y el resumen que los vincula
está en `review/`. Transportar la raíz completa para revalidar las cuatro etapas.

## Ecuaciones

Por activo y cuenta:

    observado = saldo_final - saldo_inicial
    explicado = entradas_declaradas - salidas_declaradas
    residual = observado - explicado

Las operaciones internas cancelan por activo, pero también se exige que cada
cuenta concilie. Dos errores opuestos no se ocultan por un total agregado cero.
El extremo `null` representa el exterior del perímetro declarado, no se infiere
que sea una emisión o quema. El modelo es de efectos agregados, NO una secuencia
de transacciones alcanzable; no comprueba solvencia intermedia ni autorización.

Cada activo exige decimales explícitos y dirección única dentro de la cadena
indicada. Se admite 0–255 decimales. Los saldos y movimientos son cadenas
canónicas de unidades mínimas uint256; no se usan floats. Un saldo ausente
bloquea la entrada; no se reemplaza con cero.

La implementación principal suma enteros y formatea valores en base diez. La
referencia reconstruye cada celda por otra ruta con Decimal y precisión 512,
con un contexto nuevo que no hereda precisión, exponentes o redondeo del llamador,
activando la excepción Inexact. El dominio de entrada acota valores, tamaños y
escalas. Se exige coincidencia de todas las celdas, totales y valoraciones.
Comparten el esquema y el modelo: NO son dos observadores de blockchain ni
una demostración formal de ausencia de errores.

## Estados y cobertura

- ACCOUNTING_RECONCILED: todas las celdas coinciden con los flujos cuya cobertura
  el operador DECLARA completa. No autentica la cobertura ni el estado.
- ACCOUNTING_MISMATCH: hay residuos en un conjunto declarado completo. Son
  diferencias contables, no hallazgos de seguridad automáticamente confirmados.
- ACCOUNTING_INCONCLUSIVE: la cobertura se declara incompleta, incluso si los
  residuos son cero. No se completa la evidencia mediante suposiciones.
- ACCOUNTING_ERROR: esquema o evidencia inválidos, desacuerdo de cálculos o IO.

Las cotizaciones USD son opcionales, suministradas por el operador. Se conservan
fecha y referencia de origen declaradas, pero NO se verifican fuente ni frescura.
Se usa un único precio de referencia por activo para valorar deltas; no se
modela deslizamiento, liquidez ejecutable ni P&L de mercado. Si falta un precio,
el total USD queda null, no cero. La valoración puede quedar incompleta aunque
la conciliación de unidades mínimas sea correcta.

Rebases, fees, burns y otras mecánicas no se deducen automáticamente. Deben
aparecer como efectos explícitos o quedar como diferencias sin explicar. Nunca
se usa una diferencia para asignar final_severity o completar Reconstruction
con un impacto inventado. Esos campos permanecen null/no verificados.

## Ejecución

Desde la raíz de la entrega acumulativa, Python 3.11+, POSIX y PyYAML para las
fuentes nativas ya fijadas:

```bash
python3 -m superhunter reconcile-balances --input /privado/ledger.json --out /privado/case-001
python3 -m superhunter verify-balances --bundle /privado/case-001
python3 -m superhunter review-platform --out /privado/review-001
python3 -m superhunter verify-platform --bundle /privado/review-001
```

El paquete de entrega incluye ejemplos JSON completos, etiquetados como
sintéticos, fuera del código. Los valores de precio, direcciones y anclajes de
los ejemplos NO representan lecturas reales. No se necesitan llaves ni fondos.
No se instala software, abre redes ni envía transacciones.

Cada directorio debe ser nuevo y estar fuera del checkout. Archivos 0600 y
carpeta 0700. La CLI conserva los bytes originales del input; la identidad del
modelo usa JSON canónico y el manifiesto conserva el hash de los bytes exactos.
Los mensajes de error no repiten argumentos o datos privados. El paquete sigue
siendo privado: su contenido JSON incluye los datos originales.

Salida de proceso: 0 para conciliación completa declarada; 1 para discrepancia o
inconcluso; 2 para datos/evidencia/IO inválidos. Ninguno significa bounty ganado.

## Base y contexto

Base local de esta continuación: SUPERHUNTER_dominios_permisos_591.zip,
SHA256 57b6f00f6aaa9965b0b9b362ede959d946288525ad669a19ffcc57d9d1c35212.
No confundirla con la rama remota, que no contiene toda la consolidación.
Se conservan los 27, 50 y 25 IDs anteriores. El punto 37 avanza solo en
aritmética de reconciliación: no triage, severidad o impacto probado en protocolos.
Los hitos amplios de fondos en riesgo siguen pendientes.

Referencias de interfaz consultadas el 4 de noviembre de 2026:
- https://eips.ethereum.org/EIPS/eip-20 (decimals es metadato opcional).
- https://docs.python.org/3.11/library/decimal.html (aritmética decimal y trampas).

Ninguna implementación propietaria fue copiada. Las fuentes nativas originales
no se modifican. Los hashes no autentican un productor remoto ni la verdad de
los datos que suministra. Los resultados ejecutados de esta entrega se guardan
por separado en validacion/ del ZIP, no se heredan recibos históricos.

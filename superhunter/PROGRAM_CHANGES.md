# Cambios de políticas y efecto sobre expedientes

Comparación offline de dos revisiones de programas ya verificadas por
`program_registry.py`. No abre cuentas, descarga reglas, ejecuta PoCs ni envía
reportes. Las ocho etiquetas de plataforma son espacios de nombres, no ocho
conectores API. La autorización del titular y la vigencia remota siguen sin
estar autenticadas.

## Recorrido

`review-programs` → dos paquetes originales → `compare-programs` → verificación
de ambos paquetes → comparación de políticas y casos → AuditLog nativo DIABLO →
reporte y originales preservados → `verify-program-changes`.

El inventario de expedientes debe conservar exactamente los IDs y el contenido
de cada petición. Se permite reordenarlos, pero no borrar, reemplazar o cambiar
el activo de un caso para aparentar mejora. Los programas sí pueden añadirse o
retirarse; un expediente cuyo programa desaparece queda bloqueado.

Se comparan separadamente: decisión original, política anterior evaluada a la
hora de la nueva instantánea, y decisión de la nueva política. Así no se atribuye
un simple vencimiento a una modificación de reglas. No se afirma causalidad más
allá de estas reglas explícitas ni se autentica la cronología aportada.

Se registran cambios de campos, activos y exclusiones por hash; los documentos
originales permanecen en el paquete privado. Un cambio de bytes sin actualización
de sus metadatos se identifica explícitamente y no reutiliza una aprobación.
Una política nueva con revisión aún no actualizada queda bloqueada por el registro.
La comparación no cambia el estado de expedientes externos ni modifica archivos
originales: describe qué decisiones dejarían de ser elegibles en el modelo local.

## Comandos desde la raíz del paquete

```bash
python3 -m superhunter compare-programs \
  --before /privado/revision-anterior \
  --after /privado/revision-posterior \
  --out /privado/comparacion-nueva

python3 -m superhunter verify-program-changes \
  --bundle /privado/comparacion-nueva
```

Cada entrada es un paquete completo generado por `review-programs`. La salida
requiere una carpeta nueva, fuera del checkout y las entradas. Archivos 0600,
carpeta 0700; no sobrescrituras. El comando no acepta objetivos ni ejecutables.

El verificador reconstruye resultados, bitácora e informe a partir de las copias
capturadas. Después vuelve a evaluar la instantánea posterior con la hora actual.
Una comparación histórica válida puede tener TODOS sus casos caducados hoy.
Los hashes y la reconstrucción no autentican al productor ni las reglas remotas.

Salida 0: revisión local consistente sin casos bloqueados en la reevaluación.
Salida 1: revisión consistente, con casos bloqueados. Salida 2: error de esquema,
IO, evidencia o comparación. Ningún código significa permiso de pruebas activas.
Siempre `live_testing_authorized=false` y `vulnerability_confirmed=false`.

## Validación

Las pruebas incluyen exclusiones, activos retirados, revocación de participación,
ventanas cerradas, revisiones caducadas, documento cambiado sin metadatos,
conservación de casos, separación entre plataformas, captura y límites, cambios
de fuentes durante la comprobación, alteración de reportes y bitácoras, privacidad
de diagnósticos y revalidación en procesos independientes.

Hay controles de veinte programas SINTÉTICOS, distribuidos entre las ocho etiquetas.
No son cuentas inscritas ni programas externos autorizados. La ejecución específica
y los contadores se documentan en el registro de validación de esta entrega.

## Integración y límites

El componente se registra en QA, con pruebas obligatorias, y queda conectado al
registro previo, al AuditLog nativo, a los validadores de artefactos y a la CLI.
Las pruebas de este componente se ejecutan también en `review-platform` en la
versión acumulativa; eso no equivale a conectar un feed externo a esa ejecución.
No hay vigilancia en segundo plano ni actualización automática de políticas.

Los requisitos 27/50/25 se conservan. Este es un subcomponente de gestión de
programas y control de cambios; no completa el motor Hunter ni la detección EVM.

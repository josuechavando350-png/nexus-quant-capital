# Verificación exhaustiva de configuraciones de permisos

Este módulo complementa `permissions.py`; no lo sustituye. Ejecuta comprobaciones
reales sobre datos de política y no acepta resultados PASS aportados por el usuario.
No es un generador de exploits, un auditor Solidity ni un verificador SMT.

## Qué se verifica

`sh-rbac-domain-v1` contiene una política `sh-rbac-v1`, una lista de pares
usuario/rol que pueden cambiar y un presupuesto de configuraciones. Cada variable
independientemente alterna una asignación directa; lo demás permanece fijo.
Con N variables existen exactamente 2^N configuraciones en el dominio declarado.
La primera es la política inicial. Se exploran índices consecutivos, sin aleatoriedad.

En cada configuración:

1. Dos enumeradores (máscaras binarias y producto cartesiano) comprueban la misma asignación.
2. Los algoritmos existentes de cierre topológico y recorrido con bitmasks calculan permisos y deben coincidir.
3. Se comprueban todas las aserciones de acceso y reglas de separación declaradas.
4. Se evalúa cada revocación atómica cuando todos los roles a retirar están asignados.
   Se contabilizan por separado las propiedades aplicables y las no aplicables.
5. Se registra el hash de asignaciones, decisiones y comprobaciones, sin omitir configuraciones que fallan.

Una configuración que incumple se guarda como contraejemplo del MODELO, no como
una secuencia de explotación ni evidencia de que un servicio real permita llegar a ella.
El modelo no determina quién está autorizado a asignar roles. Esa cuestión requiere
otra especificación. Las propiedades no descubiertas, omitidas o mal escritas no quedan verificadas.

## Estados de salida

- `POLICY_DOMAIN_VERIFIED`: todo el dominio fue examinado, hay propiedades y todas
  tuvieron al menos una evaluación aplicable, sin incumplimientos. Solo se prueba
  esa proposición sobre las reglas suministradas y este modelo.
- `POLICY_DOMAIN_VIOLATION`: se encontró al menos una configuración incumplidora;
  consultar `coverage_complete` para saber si además se terminó el dominio.
- `POLICY_DOMAIN_INCONCLUSIVE`: no se encontró incumplimiento, pero faltó cobertura,
  no hay propiedades o alguna nunca fue ejercitada. NO es aprobación.
- `POLICY_DOMAIN_ERROR`: entrada, desacuerdo de algoritmos, evidencia o ejecución inválidos.

Los procesos devuelven 0 solo para VERIFIED, 1 para VIOLATION/INCONCLUSIVE y
2 para error. Ninguno confirma vulnerabilidades de producción.

## Esquema y uso

```text
{
  schema_version: 1,
  model: "sh-rbac-domain-v1",
  policy: <política completa documentada en PERMISSIONS.md>,
  variables: [{user: "alice", role: "approver"}, ...],
  max_states: <entero entre 1 y 4096>
}
```

Los nombres deben referir a usuarios y roles ya declarados. Se rechazan duplicados,
campos extras, ciclos de herencia, booleanos donde se necesitan enteros y referencias
inexistentes. La política inicial se valida con el componente original.

```bash
python3 -m superhunter check-permission-domain \
  --model /directorio-privado/dominio.json --out /tmp/sh-domain-001
python3 -m superhunter verify-permission-domain --bundle /tmp/sh-domain-001
```

`example_model()` proporciona un caso pedagógico de cuatro configuraciones;
`example_model(corrected=True)` hace explícita una denegación para evitar que un
preparador apruebe su propia operación. Ambos son ejemplos construidos, no descubrimientos.

## Límites y evidencia

Máximo 16 variables (65.536 configuraciones teóricas), 4.096 examinadas por
invocación, 32 roles, 16 usuarios y 64 permisos. Un presupuesto adicional de trabajo
reduce la exploración cuando la política es costosa; se registra como WORK_BUDGET
sin fingir cobertura completa. No hay reanudación ni partición de campañas en esta versión.

Se guardan como máximo 16 contraejemplos detallados, pero el número total de
configuraciones y fallos permanece completo para el tramo explorado. La cadena
por configuración vincula todas sus evaluaciones. La bitácora nativa de DIABLO
registra inicio, bloques de cobertura de 64 configuraciones y fin.

El paquete privado guarda el modelo original intacto, análisis, bitácora,
recibo ligado al código y resumen. El verificador vuelve a ejecutar la enumeración
completa permitida, los algoritmos y la comprobación semántica del registro.
No depende del archivo de entrada original. No debe existir ninguna entrada extra.
Las carpetas no se sobrescriben y los permisos son 0700/0600.

Los hashes y la bitácora no autentican un productor remoto. La concordancia de dos
implementaciones no elimina errores compartidos de especificación. No se prueba
seguridad universal, explotabilidad, reachability real, bytecode, fases temporales,
ABAC, sesiones o el comportamiento de una blockchain. NQC no calcula aquí impacto
económico: se reutiliza la integración/QA existente y el registro DIABLO, sin
atribuir este nuevo verificador a la función numérica RMC-016.

## Conexiones y continuidad

El componente `permission_domain` depende de permisos, fuentes nativas, IO y
privacidad. Está enlazado a la CLI y al gate de QA con pruebas obligatorias; los
reportes generales muestran su validación como componente. Las políticas de una
investigación particular se procesan por el comando explícito, no se buscan ni
se ejecutan objetivos automáticamente desde `review-platform`.

Avances parciales: #24 y #34; iniciativa CERTORA.R1. Ninguna capacidad amplia se
marca completa. Se preservan los 27+50+25 requisitos y todos los tests anteriores.

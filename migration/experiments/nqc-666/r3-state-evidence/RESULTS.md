# Todas las distribuciones — R3

Tiempos en **nanosegundos**, ventanas individuales; no se eliminaron outliers.

## Agrupadas

| Camino | n | Mediana | p95 | p99 | p99.9 | Máximo | Mínimo |
|---|---:|---:|---:|---:|---:|---:|---:|
| ingress_scenario|shared0 | 12288 | 3127585 | 4579887 | 6123414 | 10295934 | 52971057 | 1837646 |
| ingress_scenario|shared1 | 12288 | 2474483 | 3658305 | 4596011 | 7408657 | 16368713 | 1468956 |
| verify|shared0 | 12288 | 3101677 | 4568540 | 5850168 | 10335944 | 23036728 | 1795352 |
| verify|shared1 | 12288 | 2502995 | 3785484 | 4993081 | 7284888 | 34310908 | 1422898 |

## Corridas en orden ejecutado

| Corrida | Mediana | p95 | p99 | p99.9 | Máximo | Mediana control reloj | Máximo control reloj |
|---|---:|---:|---:|---:|---:|---:|---:|
| verify-shared0-rep0 | 3055217 | 4417135 | 5567687 | 11312543 | 14770624 | 200 | 55963 |
| verify-shared0-rep2 | 3110690 | 4545846 | 5996465 | 10609181 | 23036728 | 201 | 107500 |
| verify-shared1-rep2 | 2483186 | 3744574 | 4768978 | 6366396 | 34310908 | 201 | 175781 |
| ingress_scenario-shared1-rep1 | 2477508 | 3627279 | 4591294 | 9065133 | 16368713 | 210 | 32448 |
| verify-shared1-rep0 | 2504978 | 3767257 | 4867134 | 6577379 | 12915053 | 201 | 50736 |
| verify-shared0-rep1 | 3154646 | 4678473 | 6011027 | 8172735 | 10399539 | 210 | 44155 |
| ingress_scenario-shared0-rep2 | 3297078 | 5181292 | 7392543 | 12203879 | 15246998 | 211 | 169923 |
| verify-shared1-rep1 | 2524277 | 3892093 | 5404124 | 8889351 | 12301399 | 210 | 148201 |
| ingress_scenario-shared1-rep0 | 2439271 | 3606969 | 4733996 | 7040039 | 9380582 | 200 | 19629 |
| ingress_scenario-shared1-rep2 | 2508825 | 3729421 | 4559617 | 6514637 | 9491367 | 210 | 82673 |
| ingress_scenario-shared0-rep1 | 3044922 | 4285148 | 5244726 | 8035470 | 11053953 | 210 | 42653 |
| ingress_scenario-shared0-rep0 | 3084381 | 4349073 | 5189775 | 6718540 | 52971057 | 210 | 177854 |

La menor mediana de `ingress_scenario` frente a `verify` en corridas separadas no implica coste negativo de IPC. No se restan estas mediciones para estimar componentes; cambian las condiciones de ejecución.

## Reutilización por paquete

| Fixture | Bytes | Referencias a nodos | Decodificaciones únicas |
|---|---:|---:|---:|
| synthetic-00.json | 9223 | 24 | 13 |
| synthetic-01.json | 14614 | 27 | 17 |
| synthetic-02.json | 18857 | 31 | 19 |
| synthetic-03.json | 23490 | 36 | 27 |
| synthetic-04.json | 9215 | 24 | 13 |
| synthetic-05.json | 14298 | 24 | 15 |
| synthetic-06.json | 19300 | 34 | 23 |
| synthetic-07.json | 23702 | 38 | 29 |
| synthetic-08.json | 9425 | 21 | 11 |
| synthetic-09.json | 14677 | 29 | 19 |
| synthetic-10.json | 19331 | 31 | 21 |
| synthetic-11.json | 23181 | 34 | 22 |
| synthetic-12.json | 9366 | 26 | 14 |
| synthetic-13.json | 15109 | 25 | 17 |
| synthetic-14.json | 19006 | 31 | 19 |
| synthetic-15.json | 24071 | 36 | 24 |

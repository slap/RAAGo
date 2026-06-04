# Plan para probar TrueSkill Through Time en RAAGo

Este documento resume el estado encontrado en el repositorio y deja un plan
operativo para probar el modelo nuevo en local y despues llevarlo a un servidor
nuevo de staging.

## Contexto

- Repositorio actual: `https://github.com/elsantodel90/RAAGo.git`
- Rama local actual observada: `master`
- El codigo en `master` no contiene TrueSkill.
- El modelo nuevo esta en el Pull Request abierto:
  - PR: https://github.com/elsantodel90/RAAGo/pull/43
  - Titulo: `Trueskill Through Time Ranking System`
  - Rama origen: `sdandois:trueskill`
  - Commit head observado: `2008eb85a616ab7c2800c545be7ae807eecdb708`

El PR #43 agrega una implementacion basada en `trueskillthroughtime` y cambia el
flujo de actualizacion de rankings para que el boton actual `Run ratings update`
corra TrueSkill Through Time.

## Archivos importantes del PR

- `aago_ranking/ratings/trueskill/tttratings.py`
  - Contiene la logica principal de TrueSkill Through Time.
  - Arriba del archivo estan las constantes del modelo para ajustar parametros:
    `EPSILON`, `ITERATIONS`, `BETA`, `MU`, `SIGMA`, `GAMMA`, `HANDI_SIGMA`,
    `HANDI1_MU`, `MU_0`.

- `aago_ranking/ratings/tasks.py`
  - Agrega funciones para crear un DataFrame de partidas y calcular ratings TTT.
  - Cambia el alias final a:

```python
run_ratings_update = run_ratings_update_ttt
```

- `requirements/base.txt`
  - Agrega:

```text
trueskillthroughtime==1.1.0
```

Nota: el PR usa `pandas`, pero en el diff observado no queda claro que este
agregado al archivo de requirements. Si falla por `ModuleNotFoundError: pandas`,
instalarlo y agregarlo a requirements.

## Advertencia importante sobre datos

El PR #43 no es solamente una vista comparativa. El flujo nuevo borra todos los
ratings existentes antes de recalcular:

```python
PlayerRating.objects.all().delete()
```

Por eso no conviene correrlo contra produccion ni contra una base de datos unica
sin backup. Probar primero con una copia local o una base de staging restaurada
desde backup.

## Como traer la rama del PR

Desde el root del repo:

```powershell
git fetch origin refs/pull/43/head:refs/remotes/origin/pr/43
git switch -c trueskill-pr43 origin/pr/43
```

Si la rama local ya existe:

```powershell
git switch trueskill-pr43
git fetch origin refs/pull/43/head:refs/remotes/origin/pr/43
git reset --hard origin/pr/43
```

Usar `git reset --hard` solo si no hay cambios locales que preservar en esa
rama.

## Prueba local recomendada

Objetivo: poder correr el modelo nuevo con datos copiados, sin tocar produccion.

1. Crear/activar entorno Python.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Instalar dependencias.

```powershell
pip install -r requirements/base.txt
pip install pandas
```

3. Configurar una base local.

El proyecto usa `DATABASE_URL`. Ejemplo con MySQL local, segun el `launch.json`
del PR:

```powershell
$env:DATABASE_URL="mysql://santi:password@localhost:3306/raago"
$env:DJANGO_DEBUG="True"
```

Tambien se puede usar otra DB local si el proyecto ya esta configurado para eso.
Lo importante es que sea una copia de datos, no produccion.

4. Ejecutar migraciones si hace falta.

```powershell
python manage.py migrate
```

5. Correr tests del modulo TrueSkill.

```powershell
python manage.py test aago_ranking.ratings.trueskill
```

El test observado en el PR es basico: calcula ratings sobre un CSV de ejemplo,
pero no tiene asserts fuertes. Sirve como prueba de humo.

6. Correr el recalculo completo en la DB local/copia.

```powershell
python manage.py shell -c "from aago_ranking.ratings.tasks import run_ratings_update; print(run_ratings_update())"
```

Resultado esperado: devuelve un dict con:

```text
message
log_evidence
mean_evidence
```

## Como probar desde el admin

En el PR, el boton existente del admin sigue siendo el punto de entrada:

- Template: `aago_ranking/templates/admin/ratings/change_list.html`
- URL: `ratings:run_ratings_update`
- Vista: `aago_ranking/ratings/views.py`
- Funcion llamada: `tasks.run_ratings_update()`

Como el PR redefine `run_ratings_update = run_ratings_update_ttt`, presionar el
boton `Run ratings update` ejecuta el modelo TrueSkill Through Time.

No usar este boton contra una DB que no se pueda borrar/recalcular.

## Recomendacion antes de deploy

El PR parece mas un prototipo/discusion que una version lista para produccion.
Antes de subirlo a un servidor publico, conviene hacer una rama propia basada en
el PR y agregar algunos resguardos.

Cambios recomendados:

1. Agregar `pandas` a requirements si no esta.

2. Crear un management command explicito, por ejemplo:

```powershell
python manage.py run_ttt_ratings
```

3. Agregar modo de comparacion sin pisar ratings actuales:

```powershell
python manage.py run_ttt_ratings --dry-run --output ratings_ttt.csv
```

4. Idealmente guardar los resultados nuevos en otra tabla, por ejemplo:

```text
TrueSkillPlayerRating
```

En vez de pisar `PlayerRating`. Esto permite comparar:

- ranking actual AGA/RAAGo
- ranking nuevo TrueSkill Through Time

5. Agregar tests minimos con asserts:

- que el calculo no explota con un set pequeno de partidas
- que devuelve columnas esperadas
- que no genera ratings para jugadores ficticios `handi_0` / `handi_1`
- que respeta partidas ganadas por negro/blanco

## Plan para servidor nuevo

Primero subir a staging, no produccion.

Servidor recomendado para la primera etapa:

- VPS chico o instancia cloud simple.
- Python compatible con el proyecto.
- Base de datos local o administrada.
- Acceso SSH.
- Backups faciles.

Pasos:

1. Crear servidor staging.
2. Clonar repo.
3. Traer PR #43 o rama propia basada en PR #43.
4. Configurar `.env` / variables:
   - `DATABASE_URL`
   - `DJANGO_DEBUG`
   - `DJANGO_ALLOWED_HOSTS`
   - secrets necesarios del proyecto
5. Restaurar dump de la DB actual.
6. Instalar requirements.
7. Correr migraciones.
8. Correr el comando de TrueSkill sobre esa copia.
9. Revisar ranking resultante.
10. Comparar con ranking viejo antes de decidir produccion.

## Comandos utiles de inspeccion

Listar PR refs disponibles:

```powershell
git ls-remote origin refs/pull/*/head
```

Ver resumen del PR #43 contra master:

```powershell
git fetch origin refs/pull/43/head:refs/remotes/origin/pr/43
git show --stat --oneline origin/master..origin/pr/43
```

Buscar referencias a TrueSkill dentro del PR:

```powershell
git grep -n -i "trueskill\|true[ -]skill\|rate_1vs1\|openskill" origin/pr/43
```

## Decision recomendada

Empezar local con una copia de datos. Despues armar staging. No desplegar el PR
directo como reemplazo del sistema actual hasta tener comparacion de rankings y
un mecanismo para no borrar datos sin backup.


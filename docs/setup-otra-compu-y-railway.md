# Setup en otra compu + plan de deploy a Railway

Documento para pasarle a Claude en otra computadora. Tiene dos partes:

- **Parte A** — levantar el entorno de desarrollo local (igual que en la compu original):
  MySQL en Docker + Django en un venv del host.
- **Parte B** — qué queremos hacer para deployar a Railway.

Contexto: app Django (RAAGo, ranking de Go). La rama de trabajo es **`trueskill-pr43`**.
La base es **MySQL** (NO Postgres; ignorar `docker-compose.yml` / `dev.yml` viejos, están
obsoletos). El dump de datos viene versionado en el repo y se carga solo.

---

## Parte A — Setup local en la otra compu

### Requisitos previos (instalar a mano si faltan)
- **Docker Desktop** (corriendo).
- **Python 3.12–3.14** (probado con 3.14). En Windows, vía el `py` launcher.
- **git**.
- **WSL con Ubuntu** (solo Windows) — necesario para compilar/correr el binario C++ `raago`
  del sistema de ranking AGA viejo. En Mac/Linux no hace falta WSL (compila nativo).

> Importante: cloná el repo en una carpeta llamada **`web-RAAGo`**. El nombre del
> contenedor de la DB (`web-raago-db-1`) depende de eso y está referenciado en el
> setting `DB_DUMP_COMMAND`. Si usás otro nombre de carpeta, hay que sobreescribir
> `DB_DUMP_COMMAND` en el `.env` con el nombre real del contenedor.

### Pasos

1. **Clonar y pararse en la rama:**
   ```powershell
   git clone <URL-del-repo> web-RAAGo
   cd web-RAAGo
   git switch trueskill-pr43
   ```

2. **Levantar MySQL en Docker** (carga el dump automáticamente la primera vez):
   ```powershell
   docker compose -f docker-compose.dev.yml up -d
   ```
   El dump `dumps/RAAGo-2026-06-05.sql` se carga vía `/docker-entrypoint-initdb.d`.
   Esperar a que el contenedor esté `healthy` (`docker ps`). Para recargar desde cero:
   `docker compose -f docker-compose.dev.yml down -v` y volver a `up`.

3. **Crear el `.env`** en la raíz del proyecto (está gitignoreado, no viene en el clone).
   Contenido exacto:
   ```dotenv
   DJANGO_SETTINGS_MODULE=config.settings.local
   DJANGO_DEBUG=True
   DJANGO_SECRET_KEY=dev-only-not-secret
   DATABASE_URL=mysql://raago:raago@127.0.0.1:3306/raago

   # Binario AGA (raago): ELF Linux compilado en WSL, se invoca vía WSL.
   RAAGO_COMMAND=wsl.exe,-e,./original-AGA-rating-system/aago-rating-calculator/raago
   ```
   (En Mac/Linux, omitir `RAAGO_COMMAND`: usa el binario nativo por default.)

4. **Crear venv e instalar dependencias:**
   ```powershell
   py -3.14 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install --upgrade pip wheel
   .\.venv\Scripts\python.exe -m pip install -r requirements/local.txt
   ```
   (`mysqlclient` tiene wheel para 3.14; si la versión de Python no tuviera wheel,
   usar Python 3.12/3.13.)

5. **Migrar** (el dump trae el estado viejo de migraciones; esto aplica allauth,
   la alineación con Django 5.2 y la tabla de TrueSkill):
   ```powershell
   .\.venv\Scripts\python.exe manage.py migrate
   ```

6. **Compilar el binario `raago`** (sistema de ranking AGA viejo) en WSL:
   ```powershell
   wsl -u root bash -c "apt-get update && apt-get install -y build-essential libgsl-dev"
   wsl -e bash -c "cd '/mnt/c/<ruta>/web-RAAGo/original-AGA-rating-system/aago-rating-calculator' && make"
   ```
   Reemplazar `<ruta>` por la ruta real (ej. `Users/<usuario>/Documents/GitHub/...`).
   La única dependencia real es **GSL** (`libgsl-dev`); el `-I mysql` del makefile es
   vestigial. Verificar: `wsl -e file <.../raago>` debe decir "ELF 64-bit ... executable".
   (En Mac/Linux: `sudo apt install libgsl-dev build-essential && make` en esa carpeta,
   sin WSL.)

7. **Crear un superusuario** para el admin (la DB del dump no trae uno con password conocida):
   ```powershell
   .\.venv\Scripts\python.exe manage.py shell -c "from aago_ranking.users.models import User; u,_=User.objects.get_or_create(username='admin', defaults={'email':'admin@local.dev'}); u.is_staff=u.is_superuser=True; u.set_password('admin'); u.save(); print('admin/admin listo')"
   ```

8. **Arrancar el server:**
   ```powershell
   .\.venv\Scripts\python.exe manage.py runserver
   ```
   Abrir http://127.0.0.1:8000/ (sitio) y http://127.0.0.1:8000/admin/ (admin, `admin/admin`).

### Verificación rápida
- `http://127.0.0.1:8000/` → ranking AGA (de siempre).
- `http://127.0.0.1:8000/comparacion/` → AGA vs TrueSkill.
- Tests TrueSkill: `.\.venv\Scripts\python.exe manage.py test aago_ranking.ratings.trueskill`.
- Recalcular TrueSkill (tabla separada, no pisa el ranking viejo):
  `.\.venv\Scripts\python.exe manage.py run_ttt_ratings`
- Admin → sección **Ratings** tiene dos botones:
  - **Run ratings update** → recalcula el ranking AGA viejo (corre `raago` vía WSL).
  - **Download DB dump** → descarga un `.sql` (mysqldump) listo para subir a la web de la AAGo.
    Excluye las tablas `socialaccount_*` (tienen columnas `json` que el MySQL viejo de la
    AAGo no soporta).

### Notas / gotchas
- Si tocás `urls.py` o settings y ves algo raro (ej. `NoReverseMatch`), **reiniciá el
  `runserver`**: el autoreload en Windows a veces no toma esos cambios.
- El binario `raago` y el `.env` están gitignoreados: hay que rehacerlos en cada compu
  (pasos 3 y 6).

---

## Parte B — Deploy a Railway (lo que queremos hacer)

Objetivo: hostear el sistema en **Railway** usando un **Dockerfile** (no el buildpack
automático), porque hay que compilar el binario C++ `raago` (necesita GSL) y tener
`mysqldump` para el botón de descarga. cPanel/shared hosting no sirve para esto (sin root,
sin compilar, sin libs de sistema); Railway con Dockerfile o un VPS, sí.

### Por qué el binario no es problema en Railway
Railway corre contenedores **Linux**, así que `raago` se compila y ejecuta **nativo**
(sin WSL). El setting `RAAGO_COMMAND` ya tiene como default el binario nativo, así que
allá no se toca.

### Tareas para el deploy
1. **Escribir un `Dockerfile`** que:
   - parta de `python:3.12-slim` (o similar),
   - instale dependencias de sistema y compile raago:
     ```dockerfile
     RUN apt-get update && apt-get install -y --no-install-recommends \
         build-essential libgsl-dev default-mysql-client \
       && rm -rf /var/lib/apt/lists/*
     COPY . /app
     WORKDIR /app
     RUN make -C original-AGA-rating-system/aago-rating-calculator
     RUN pip install --no-cache-dir -r requirements/production.txt
     RUN python manage.py collectstatic --noinput
     CMD gunicorn config.wsgi --bind 0.0.0.0:$PORT
     ```
     (`default-mysql-client` es para el botón Download DB dump.)
2. **Agregar MySQL gestionado** en Railway (inyecta `DATABASE_URL`).
3. **Variables de entorno** en el servicio Django:
   - `DJANGO_SETTINGS_MODULE=config.settings.production`
   - `DJANGO_SECRET_KEY=<secreto largo y random>`
   - `DJANGO_ALLOWED_HOSTS=<dominio de railway / propio>`
   - `DJANGO_CSRF_TRUSTED_ORIGINS=https://<dominio>`
   - `DATABASE_URL` → la provee Railway.
   - `DB_DUMP_COMMAND` → apuntar al **mysqldump nativo** contra la DB gestionada (NO el
     `docker exec` del default local). Ej. (separado por comas):
     `mysqldump,-h,<host>,-P,<port>,-u,<user>,-p<pass>,--no-tablespaces,--single-transaction,--ignore-table=<db>.socialaccount_socialaccount,--ignore-table=<db>.socialaccount_socialapp,--ignore-table=<db>.socialaccount_socialapp_sites,--ignore-table=<db>.socialaccount_socialtoken,<db>`
   - (`RAAGO_COMMAND` NO hace falta: el default usa el binario nativo compilado en la imagen.)
4. **Cargar el dump inicial** en la DB de Railway una vez (importar un `.sql` del dump).
5. **Estáticos**: ya servidos por WhiteNoise (configurado en `production.py`); `collectstatic`
   corre en el build.
6. **Recálculo largo**: el botón "Run ratings update" recorre los ~171 eventos y puede
   exceder timeouts de HTTP. Para producción conviene correrlo como **management command /
   job** en vez de esperar en la request (o moverlo a un worker celery). Pendiente de definir.

### Alternativa
Un **VPS** (Hostinger VPS u otro) también sirve y da control total: clonar repo, instalar
deps + GSL, compilar raago, gunicorn + nginx, MySQL local o gestionado. Es el camino
"server propio". cPanel shared NO (por el binario y las libs de sistema).

---

## Referencia rápida de datos del proyecto
- Rama: `trueskill-pr43`
- DB local: MySQL 8 en Docker — db/usuario/pass = `raago`, root = `root`, puerto `3306`.
- Contenedor: `web-raago-db-1` (depende de que la carpeta sea `web-RAAGo`).
- Dump versionado: `dumps/RAAGo-2026-06-05.sql` (se carga solo en el primer `up`).
- Superusuario admin local: `admin` / `admin` (crear con el paso 7).
- Settings: `config.settings.local` (dev) / `config.settings.production` (server).
- TrueSkill se calcula con `manage.py run_ttt_ratings` → tabla `TrueSkillPlayerRating`
  (separada, no pisa `PlayerRating`).

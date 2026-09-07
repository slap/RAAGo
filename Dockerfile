# Imagen de producción para Railway (o cualquier host con Docker).
# Compila el binario C++ `raago` (necesita GSL) y trae mysqldump para el
# botón "Download DB dump". Django corre con gunicorn + WhiteNoise.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

# Dependencias de sistema:
#  - build-essential + libgsl-dev: compilar el binario raago (BayRate, usa GSL)
#  - default-libmysqlclient-dev + pkg-config: compilar mysqlclient (pip)
#  - default-mysql-client: provee mysqldump para el botón Download DB dump
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgsl-dev \
        default-libmysqlclient-dev \
        default-mysql-client \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python primero (mejor cache de capas)
COPY requirements/ requirements/
RUN pip install --upgrade pip && pip install -r requirements/production.txt

# Resto del código
COPY . .

# Compilar el binario raago (nativo Linux, sin WSL)
RUN make -C original-AGA-rating-system/aago-rating-calculator

# collectstatic en build con valores dummy: settings.production importa
# DJANGO_SECRET_KEY y DATABASE_URL al cargarse, pero collectstatic NO se conecta
# a la DB (solo parsea la URL), así que sirven valores de relleno.
RUN DJANGO_SECRET_KEY=build-only \
    DATABASE_URL=mysql://u:p@localhost:3306/db \
    DJANGO_SECURE_SSL_REDIRECT=False \
    python manage.py collectstatic --noinput

EXPOSE 8000

# En runtime sí hay DATABASE_URL real: migrar y levantar gunicorn.
CMD python manage.py migrate --noinput && \
    gunicorn config.wsgi --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --timeout 120

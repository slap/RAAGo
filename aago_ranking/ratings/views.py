import datetime
import subprocess

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from . import tasks


@staff_member_required
@require_http_methods(["POST"])
def run_ratings_update(_request):
    json = tasks.run_ratings_update()
    return JsonResponse(json)


@staff_member_required
@require_http_methods(["GET"])
def download_db_dump(_request):
    """Genera un dump mysqldump de la base y lo ofrece como descarga.

    El comando se configura en settings.DB_DUMP_COMMAND (por defecto corre
    mysqldump dentro del contenedor Docker local).
    """
    try:
        result = subprocess.run(
            settings.DB_DUMP_COMMAND,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except FileNotFoundError as exc:
        return HttpResponse(
            "No se pudo ejecutar el comando de dump ({}): {}".format(
                settings.DB_DUMP_COMMAND, exc),
            status=500, content_type="text/plain; charset=utf-8")
    except subprocess.CalledProcessError as exc:
        return HttpResponse(
            "mysqldump fallo (codigo {}):\n{}".format(
                exc.returncode, exc.stderr.decode("utf-8", "replace")),
            status=500, content_type="text/plain; charset=utf-8")

    filename = "RAAGo-{}.sql".format(datetime.date.today().isoformat())
    response = HttpResponse(result.stdout, content_type="application/sql")
    response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
    return response

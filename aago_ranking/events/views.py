
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from . import tasks

@staff_member_required
@require_http_methods(["POST"])
def upload_event_file(request):
    event_file = request.FILES.get("event_file")
    if event_file is None:
        return JsonResponse(
            {"error": "No se seleccionó ningún archivo para subir."},
            status=400,
        )
    json = tasks.upload_event_file(event_file)
    return JsonResponse(json)

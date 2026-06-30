from django.urls import re_path as url

from . import views

app_name = 'ratings'

urlpatterns = [
    url(r'^rating-job-status/(?P<job_id>\d+)$', views.rating_job_status, name='rating_job_status'),
    url(r'run-ttt-ratings-update', views.run_ttt_ratings_update, name='run_ttt_ratings_update'),
    url(r'run-ratings-update', views.run_ratings_update, name='run_ratings_update'),
    url(r'download-db-dump', views.download_db_dump, name='download_db_dump'),
]

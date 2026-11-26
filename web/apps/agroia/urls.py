from django.urls import path

from apps.agroia import views

app_name = "agroia"

urlpatterns = [
    path("agroia/", views.inicio, name="inicio"),
    path("agroia/nueva/", views.nueva, name="nueva"),
    # El widget flotante, antes de agroia/<id>/ (si no, «widget» se tomaría como un id).
    path("agroia/widget/", views.widget, name="widget"),
    path("agroia/widget/preguntar/", views.widget_preguntar, name="widget_preguntar"),
    path("agroia/widget/reiniciar/", views.widget_reiniciar, name="widget_reiniciar"),
    path("agroia/<str:conversacion_id>/", views.ver, name="ver"),
    path("agroia/<str:conversacion_id>/preguntar/", views.preguntar, name="preguntar"),
    path("agroia/<str:conversacion_id>/reintentar/", views.reintentar, name="reintentar"),
    path("agroia/<str:conversacion_id>/solicitud/", views.solicitud, name="solicitud"),
    path("agroia/<str:conversacion_id>/borrar/", views.borrar, name="borrar"),
]

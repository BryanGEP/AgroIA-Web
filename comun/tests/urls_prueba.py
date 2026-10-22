"""Vistas mínimas para probar autenticación, permisos y errores de comun."""

from django.http import Http404
from django.urls import path
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from agroia_comun.errores import ErrorDeNegocio
from agroia_comun.permisos import (
    CorreoVerificado,
    EsAdministrador,
    EsCliente,
    EsDuenoOAdmin,
    usuario_id,
)


class Objeto:
    def __init__(self, dueno: int):
        self.usuario_id = dueno


class Protegida(APIView):
    def get(self, request):
        return Response({"usuario_id": usuario_id(request)})


class SoloAdmin(APIView):
    permission_classes = [EsAdministrador]

    def get(self, request):
        return Response({"ok": True})


class SoloCliente(APIView):
    permission_classes = [IsAuthenticated, EsCliente, CorreoVerificado]

    def get(self, request):
        return Response({"ok": True})


class DeUnDueno(APIView):
    permission_classes = [IsAuthenticated, EsDuenoOAdmin]

    def get(self, request, dueno: int):
        self.check_object_permissions(request, Objeto(dueno))
        return Response({"ok": True})


class EjemploSerializer(serializers.Serializer):
    cantidad = serializers.IntegerField(min_value=1)


class ConErrores(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        caso = request.data.get("caso")
        if caso == "negocio":
            raise ErrorDeNegocio("stock_insuficiente", "Solo quedan 2 piezas.")
        if caso == "no_existe":
            raise Http404
        EjemploSerializer(data=request.data).is_valid(raise_exception=True)
        return Response({"ok": True})


urlpatterns = [
    path("protegida/", Protegida.as_view()),
    path("admin/", SoloAdmin.as_view()),
    path("cliente/", SoloCliente.as_view()),
    path("dueno/<int:dueno>/", DeUnDueno.as_view()),
    path("errores/", ConErrores.as_view()),
]

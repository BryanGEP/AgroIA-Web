"""Comando crear_indices: crea los índices de la definición técnica y se puede repetir."""

from django.core.management import call_command


def test_crea_los_indices_y_se_puede_repetir(mongo_simulado):
    call_command("crear_indices", verbosity=0)
    call_command("crear_indices", verbosity=0)

    def claves(coleccion: str) -> list:
        return [i["key"] for i in mongo_simulado[coleccion].index_information().values()]

    assert [("usuario_id", 1), ("actualizada_en", -1)] in claves("conversaciones")
    assert [("usuario_id", 1), ("creado_en", -1)] in claves("diagnosticos")
    assert [("tipo", 1), ("fecha", -1)] in claves("bitacora")

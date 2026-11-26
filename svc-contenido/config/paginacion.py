"""Paginación de consultas de MongoDB con el PageNumberPagination de DRF.

`ConsultaMongo` se comporta como la lista que espera el paginador de Django: sabe
contar (`count`) y cortar (`[inicio:fin]` con skip/limit). Así la respuesta tiene el
mismo formato que en svc-tienda: `{"count", "next", "previous", "results"}`.
"""

from pymongo.collection import Collection


class ConsultaMongo:
    def __init__(
        self,
        coleccion: Collection,
        filtro: dict,
        orden: list[tuple[str, int]],
        proyeccion: dict | None = None,
    ):
        self.coleccion = coleccion
        self.filtro = filtro
        self.orden = orden
        self.proyeccion = proyeccion

    def count(self) -> int:
        return self.coleccion.count_documents(self.filtro)

    def __len__(self) -> int:
        return self.count()

    def __getitem__(self, corte: slice) -> list[dict]:
        if not isinstance(corte, slice):
            raise TypeError("ConsultaMongo solo admite cortes [inicio:fin].")
        inicio = corte.start or 0
        cursor = self.coleccion.find(self.filtro, self.proyeccion).sort(self.orden).skip(inicio)
        if corte.stop is not None:
            cursor = cursor.limit(corte.stop - inicio)
        return list(cursor)

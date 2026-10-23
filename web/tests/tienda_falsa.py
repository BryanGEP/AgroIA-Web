"""svc-tienda simulado para las pruebas de web (httpx.MockTransport)."""

import json

import httpx

CATEGORIAS = [
    {"id": 1, "nombre": "Fungicidas", "slug": "fungicidas", "descripcion": "", "activa": True},
    {"id": 2, "nombre": "Riego", "slug": "riego", "descripcion": "", "activa": True},
]


def producto(slug: str = "caldo-bordeles", **cambios) -> dict:
    datos = {
        "id": 1,
        "nombre": "Caldo bordelés 1 kg",
        "slug": slug,
        "categoria": "fungicidas",
        "descripcion": "Mezcla de sulfato de cobre y cal.",
        "precio": "1250.50",
        "stock": 35,
        "unidad": "kg",
        "imagen": None,
        "ficha_tecnica": {
            "ingrediente_activo": "Sulfato de cobre",
            "composicion": {"Cu": "25%", "Ca": "10%"},
            "tallas": ["M", "G"],
            "proteccion_uv": True,
        },
        "activo": True,
        "disponible": True,
        "creado_en": "2026-10-22T10:00:00-06:00",
    }
    datos.update(cambios)
    return datos


class TiendaFalsa:
    """Responde como svc-tienda y guarda las peticiones que recibió."""

    def __init__(self):
        self.peticiones: list[httpx.Request] = []
        self.productos = [
            producto(),
            producto("manguera", nombre="Manguera de goteo", categoria="riego", stock=4),
        ]
        self.caida = False
        self.imagenes: dict[str, tuple[bytes, str]] = {}
        self.conteo: int | None = None  # para simular más páginas

    def __call__(self, peticion: httpx.Request) -> httpx.Response:
        self.peticiones.append(peticion)
        if self.caida:
            raise httpx.ConnectError("svc-tienda caído")
        ruta = peticion.url.path
        if ruta == "/api/v1/categorias/":
            return httpx.Response(
                200, json={"count": 2, "next": None, "previous": None, "results": CATEGORIAS}
            )
        if ruta == "/api/v1/productos/":
            if peticion.url.params.get("page", "1") not in ("1",):
                return httpx.Response(404, json={"error": "no_encontrado", "detalle": "x"})
            return httpx.Response(
                200,
                json={
                    "count": self.conteo or len(self.productos),
                    "next": None,
                    "previous": None,
                    "results": self.productos,
                },
            )
        if ruta.startswith("/api/v1/productos/"):
            slug = ruta.rstrip("/").rsplit("/", 1)[-1]
            for p in self.productos:
                if p["slug"] == slug:
                    return httpx.Response(200, json=p)
            return httpx.Response(404, json={"error": "no_encontrado", "detalle": "x"})
        if ruta.startswith("/media/"):
            clave = ruta.removeprefix("/media/")
            if clave in self.imagenes:
                contenido, tipo = self.imagenes[clave]
                return httpx.Response(200, content=contenido, headers={"content-type": tipo})
            return httpx.Response(404, text="no")
        return httpx.Response(404, text=json.dumps({"error": "no_encontrado"}))

    def parametros(self, indice: int = -1) -> dict:
        productos = [p for p in self.peticiones if p.url.path == "/api/v1/productos/"]
        return dict(productos[indice].url.params)

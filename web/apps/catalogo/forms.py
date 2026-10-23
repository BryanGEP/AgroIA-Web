from django import forms

ORDENES = [
    ("", "Más recientes"),
    ("precio", "Precio: menor a mayor"),
    ("-precio", "Precio: mayor a menor"),
    ("nombre", "Nombre"),
]


class FiltrosCatalogo(forms.Form):
    """Filtros del catálogo. Se validan aquí antes de enviarlos a svc-tienda."""

    q = forms.CharField(label="Buscar", max_length=100, required=False)
    categoria = forms.ChoiceField(label="Categoría", required=False)
    precio_min = forms.DecimalField(
        label="Precio mínimo", min_value=0, max_digits=10, decimal_places=2, required=False
    )
    precio_max = forms.DecimalField(
        label="Precio máximo", min_value=0, max_digits=10, decimal_places=2, required=False
    )
    disponible = forms.BooleanField(label="Solo con existencias", required=False)
    orden = forms.ChoiceField(label="Ordenar por", choices=ORDENES, required=False)

    def __init__(self, *args, categorias: list[dict] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        opciones = [(c["slug"], c["nombre"]) for c in categorias or []]
        self.fields["categoria"].choices = [("", "Todas"), *opciones]

    def clean(self):
        datos = super().clean()
        minimo, maximo = datos.get("precio_min"), datos.get("precio_max")
        if minimo is not None and maximo is not None and minimo > maximo:
            self.add_error("precio_max", "Debe ser mayor o igual que el precio mínimo.")
        return datos

    def parametros(self) -> dict:
        """Parámetros para svc-tienda con los filtros válidos."""
        datos = self.cleaned_data if self.is_bound and hasattr(self, "cleaned_data") else {}
        params = {}
        if datos.get("q"):
            params["q"] = datos["q"]
        if datos.get("categoria"):
            params["categoria"] = datos["categoria"]
        for campo in ("precio_min", "precio_max"):
            if datos.get(campo) is not None and campo not in self.errors:
                params[campo] = str(datos[campo])
        if datos.get("disponible"):
            params["disponible"] = "true"
        if datos.get("orden"):
            params["ordering"] = datos["orden"]
        return params

    @property
    def hay_filtros(self) -> bool:
        return bool(self.parametros())

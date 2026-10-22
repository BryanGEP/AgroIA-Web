"""Carga categorías y productos de demostración para el cultivo del aguacate.

    docker compose exec svc-tienda python manage.py cargar_datos_demo

Se puede correr varias veces: actualiza por slug y no duplica. Restablece precio, stock
y ficha técnica de los productos de demostración a sus valores originales.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalogo.models import Categoria, Producto

CATEGORIAS = [
    ("fungicidas", "Fungicidas", "Prevención y control de antracnosis, roña y otras enfermedades."),
    ("fertilizantes", "Fertilizantes", "Nutrición al suelo y foliar para huertas de aguacate."),
    ("herramientas", "Herramientas", "Poda, cosecha y trabajo diario en la huerta."),
    ("riego", "Riego", "Riego por goteo y microaspersión."),
    ("proteccion", "Protección", "Equipo de protección personal y para el cultivo."),
]

# (slug, categoría, nombre, precio, stock, unidad, descripción, ficha técnica)
PRODUCTOS = [
    (
        "oxicloruro-de-cobre-50-ph-1-kg",
        "fungicidas",
        "Oxicloruro de cobre 50% PH 1 kg",
        "245.00",
        40,
        "kg",
        "Fungicida preventivo de contacto para antracnosis y roña del aguacate.",
        {
            "ingrediente_activo": "Oxicloruro de cobre 50%",
            "formulacion": "Polvo humectable",
            "dosis": "2 a 3 kg/ha",
            "intervalo_seguridad": "1 día",
            "presentacion": "Bolsa de 1 kg",
        },
    ),
    (
        "caldo-bordeles-1-kg",
        "fungicidas",
        "Caldo bordelés 1 kg",
        "185.00",
        35,
        "kg",
        "Mezcla de sulfato de cobre y cal, tradicional para prevenir hongos en follaje y fruto.",
        {
            "ingrediente_activo": "Sulfato de cobre pentahidratado + cal",
            "dosis": "1 kg en 100 L de agua",
            "presentacion": "Bolsa de 1 kg",
        },
    ),
    (
        "azoxistrobina-25-sc-1-l",
        "fungicidas",
        "Azoxistrobina 25% SC 1 L",
        "1150.00",
        12,
        "litro",
        "Fungicida sistémico para el control de antracnosis en floración y amarre de fruto.",
        {
            "ingrediente_activo": "Azoxistrobina 250 g/L",
            "formulacion": "Suspensión concentrada",
            "dosis": "0.5 a 0.75 L/ha",
            "intervalo_seguridad": "7 días",
            "categoria_toxicologica": "Ligeramente tóxico (banda verde)",
        },
    ),
    (
        "azufre-humectable-80-5-kg",
        "fungicidas",
        "Azufre humectable 80% 5 kg",
        "320.00",
        25,
        "kg",
        "Fungicida y acaricida de contacto; también corrige deficiencias de azufre.",
        {
            "ingrediente_activo": "Azufre elemental 80%",
            "dosis": "3 a 5 kg/ha",
            "presentacion": "Saco de 5 kg",
        },
    ),
    (
        "urea-46-costal-50-kg",
        "fertilizantes",
        "Urea 46% costal 50 kg",
        "690.00",
        60,
        "costal",
        "Fertilizante nitrogenado de alta concentración para la etapa de crecimiento vegetativo.",
        {
            "composicion": {"N": "46%"},
            "dosis": "Según análisis de suelo",
            "presentacion": "Costal de 50 kg",
        },
    ),
    (
        "triple-17-costal-50-kg",
        "fertilizantes",
        "Fertilizante triple 17 costal 50 kg",
        "780.00",
        45,
        "costal",
        "Fórmula balanceada de nitrógeno, fósforo y potasio para mantenimiento de la huerta.",
        {
            "composicion": {"N": "17%", "P2O5": "17%", "K2O": "17%"},
            "presentacion": "Costal de 50 kg",
        },
    ),
    (
        "nitrato-de-potasio-25-kg",
        "fertilizantes",
        "Nitrato de potasio soluble 25 kg",
        "1350.00",
        20,
        "costal",
        "Potasio y nitrógeno solubles para fertirriego en llenado de fruto.",
        {
            "composicion": {"N": "13.5%", "K2O": "46%"},
            "uso": "Fertirriego y aplicación foliar",
            "presentacion": "Saco de 25 kg",
        },
    ),
    (
        "quelato-de-zinc-y-boro-1-l",
        "fertilizantes",
        "Quelato de zinc y boro 1 L",
        "295.00",
        30,
        "litro",
        "Micronutrientes foliares para mejorar floración y amarre de fruto.",
        {"composicion": {"Zn": "5%", "B": "2%"}, "dosis": "1 a 2 L/ha", "aplicacion": "Foliar"},
    ),
    (
        "composta-de-lombriz-40-kg",
        "fertilizantes",
        "Composta de lombriz 40 kg",
        "210.00",
        50,
        "costal",
        "Abono orgánico que mejora la estructura del suelo y la retención de humedad.",
        {
            "materia_organica": "≥ 30%",
            "presentacion": "Costal de 40 kg",
            "certificacion": "Orgánico",
        },
    ),
    (
        "tijera-de-poda-profesional",
        "herramientas",
        "Tijera de poda profesional",
        "420.00",
        18,
        "pieza",
        "Tijera de una mano con hojas de acero templado para ramas de hasta 2.5 cm.",
        {"material": "Acero al carbono", "corte_maximo": "25 mm", "garantia": "1 año"},
    ),
    (
        "serrote-de-poda-curvo",
        "herramientas",
        "Serrote de poda curvo 33 cm",
        "365.00",
        15,
        "pieza",
        "Serrote de dientes triples para ramas gruesas de aguacate.",
        {"longitud_hoja": "33 cm", "material": "Acero SK5", "incluye": "Funda"},
    ),
    (
        "cortador-de-aguacate-con-bolsa",
        "herramientas",
        "Cortador de aguacate con bolsa y garrocha",
        "780.00",
        10,
        "pieza",
        "Gancho cortador con bolsa de lona para cosechar fruta alta sin golpearla.",
        {"longitud_garrocha": "Extensible hasta 4 m", "material": "Aluminio y lona"},
    ),
    (
        "bomba-aspersora-de-mochila-20-l",
        "herramientas",
        "Bomba aspersora de mochila 20 L",
        "1250.00",
        8,
        "pieza",
        "Aspersora manual para aplicación de fungicidas y foliares.",
        {"capacidad": "20 L", "presion_maxima": "6 bar", "boquillas": "Cono y abanico"},
    ),
    (
        "manguera-de-goteo-16-mm-100-m",
        "riego",
        "Manguera de goteo 16 mm, rollo 100 m",
        "890.00",
        22,
        "pieza",
        "Cintilla con goteros integrados cada 30 cm para riego por goteo.",
        {
            "diametro": "16 mm",
            "separacion_goteros": "30 cm",
            "caudal": "2 L/h",
            "longitud": "100 m",
        },
    ),
    (
        "microaspersor-giratorio-paquete-50",
        "riego",
        "Microaspersor giratorio (paquete de 50)",
        "650.00",
        16,
        "pieza",
        "Microaspersores para cubrir la zona de raíces del árbol.",
        {"caudal": "40 L/h", "radio": "3 m", "piezas": 50},
    ),
    (
        "filtro-de-anillos-1-pulgada",
        "riego",
        "Filtro de anillos 1 pulgada",
        "540.00",
        12,
        "pieza",
        "Filtro para evitar que se tapen goteros y microaspersores.",
        {"conexion": "1 pulgada", "malla": "120 mesh", "caudal_maximo": "5 m³/h"},
    ),
    (
        "tensiometro-para-suelo-30-cm",
        "riego",
        "Tensiómetro para suelo 30 cm",
        "980.00",
        6,
        "pieza",
        "Mide la humedad del suelo para decidir cuándo regar.",
        {"profundidad": "30 cm", "rango": "0 a 100 cbar"},
    ),
    (
        "guantes-de-nitrilo-par",
        "proteccion",
        "Guantes de nitrilo para agroquímicos (par)",
        "85.00",
        100,
        "pieza",
        "Guantes resistentes a químicos para preparar y aplicar productos.",
        {"material": "Nitrilo", "largo": "33 cm", "tallas": ["M", "G", "XG"]},
    ),
    (
        "mascarilla-con-filtros-para-vapores",
        "proteccion",
        "Mascarilla con filtros para vapores orgánicos",
        "560.00",
        14,
        "pieza",
        "Media cara reutilizable con cartuchos para aplicación de agroquímicos.",
        {"filtros": "Vapores orgánicos y partículas P95", "incluye_cartuchos": True},
    ),
    (
        "malla-sombra-50-4x25-m",
        "proteccion",
        "Malla sombra 50%, 4 x 25 m",
        "1450.00",
        9,
        "pieza",
        "Protege viveros y árboles jóvenes de sol intenso y granizo ligero.",
        {"sombra": "50%", "medidas": "4 x 25 m", "proteccion_uv": True},
    ),
]


class Command(BaseCommand):
    help = "Carga categorías y productos de demostración (no duplica si se corre de nuevo)."

    @transaction.atomic
    def handle(self, *args, **options):
        categorias = {}
        for slug, nombre, descripcion in CATEGORIAS:
            categorias[slug], _ = Categoria.objects.update_or_create(
                slug=slug, defaults={"nombre": nombre, "descripcion": descripcion, "activa": True}
            )

        creados = 0
        for slug, categoria, nombre, precio, stock, unidad, descripcion, ficha in PRODUCTOS:
            _, creado = Producto.objects.update_or_create(
                slug=slug,
                defaults={
                    "categoria": categorias[categoria],
                    "nombre": nombre,
                    "precio": Decimal(precio),
                    "stock": stock,
                    "unidad": unidad,
                    "descripcion": descripcion,
                    "ficha_tecnica": ficha,
                    "activo": True,
                },
            )
            creados += creado

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(CATEGORIAS)} categorías y {len(PRODUCTOS)} productos listos "
                f"({creados} productos nuevos)."
            )
        )

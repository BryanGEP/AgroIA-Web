"""markdown_seguro frente a texto no confiable (XSS).

Las respuestas del agente pueden traer texto de sus documentos y de lo que escribió el
usuario. El resultado del filtro solo puede contener las etiquetas y atributos que genera
el propio filtro: se comprueba recorriendo la salida con un parser de HTML.

El filtro no convierte enlaces: `[texto](url)` queda como texto escapado, así que no existe
ningún `href` que un `javascript:` pudiera aprovechar.
"""

import re
from html.parser import HTMLParser

import pytest

from apps.agroia.templatetags.markdown_seguro import markdown_seguro

# Lo único que el filtro puede generar: etiqueta -> valores permitidos de `class`.
PERMITIDAS = {
    "div": {None, "flex flex-col gap-2", "overflow-x-auto my-2"},
    "p": {None, "font-bold"},
    "br": {None},
    "strong": {None},
    "em": {None},
    "code": {"rounded bg-base-300 px-1"},
    "ul": {"list-disc pl-5"},
    "ol": {"list-decimal pl-5"},
    "li": {None},
    "table": {"table table-sm"},
    "thead": {None},
    "tbody": {None},
    "tr": {None},
    "th": {None},
    "td": {None},
}


class Inventario(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.etiquetas: list[tuple[str, list[tuple[str, str | None]]]] = []

    def handle_starttag(self, tag, attrs):
        self.etiquetas.append((tag, attrs))

    def handle_startendtag(self, tag, attrs):
        self.etiquetas.append((tag, attrs))


def assert_solo_lo_del_filtro(html: str) -> None:
    inventario = Inventario()
    inventario.feed(html)
    for etiqueta, atributos in inventario.etiquetas:
        assert etiqueta in PERMITIDAS, f"etiqueta no permitida: <{etiqueta}>"
        nombres = [nombre for nombre, _ in atributos]
        assert set(nombres) <= {"class"}, f"atributo no permitido en <{etiqueta}>: {nombres}"
        clase = dict(atributos).get("class")
        assert clase in PERMITIDAS[etiqueta], f"class no permitida en <{etiqueta}>: {clase!r}"


ATAQUES = {
    "script": "<script>alert(1)</script>",
    "script-mayusculas": "<ScRiPt SRC=//x.example/a.js></sCrIpT>",
    "img-onerror": '<img src=x onerror="alert(1)">',
    "svg-onload": "<svg/onload=alert(1)>",
    "atributo-on-en-etiqueta-permitida": '<p onclick="alert(1)">hola</p>',
    "strong-con-atributo": '<strong onmouseover="alert(1)">x</strong>',
    "a-javascript": '<a href="javascript:alert(1)">clic</a>',
    "iframe": '<iframe src="data:text/html,<script>alert(1)</script>"></iframe>',
    "markdown-enlace-javascript": "[clic](javascript:alert(1))",
    "markdown-enlace-mayusculas-espacios": "[clic]( JaVaScRiPt :alert(1))",
    "markdown-enlace-entidades": "[clic](&#106;avascript&#58;alert(1))",
    "markdown-enlace-data": "[clic](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)",
    "markdown-enlace-vbscript": "[clic](vbscript:msgbox(1))",
    "markdown-enlace-sin-esquema": "[clic](//sitio-ajeno.example)",
    "markdown-imagen": "![x](javascript:alert(1))",
    "html-en-negritas": "**<img src=x onerror=alert(1)>**",
    "html-en-cursiva": "*<script>alert(1)</script>*",
    "html-en-codigo": "`<script>alert(1)</script>`",
    "html-en-encabezado": "## <img src=x onerror=alert(1)>",
    "html-en-lista": "- <script>alert(1)</script>\n1. <svg onload=alert(1)>",
    "html-en-tabla": (
        '| a | b |\n|---|---|\n| <img src=x onerror=alert(1)> | <a href="javascript:x">y</a> |'
    ),
    "markdown-anidado": "***<b>x</b>*** **a *b `<i onclick=x>c</i>` d* e** `**no**`",
    "cierre-de-atributo": '`" onmouseover="alert(1)` y **" onclick="x"**',
    "entidades": "&lt;script&gt;alert(1)&lt;/script&gt; &#60;img src=x onerror=alert(1)&#62;",
    "style": '<style>body{display:none}</style><p style="color:red">x</p>',
}


@pytest.mark.parametrize("texto", ATAQUES.values(), ids=ATAQUES.keys())
def test_solo_contiene_lo_que_genera_el_filtro(texto):
    assert_solo_lo_del_filtro(markdown_seguro(texto))


@pytest.mark.parametrize("texto", ATAQUES.values(), ids=ATAQUES.keys())
def test_todo_menor_que_es_de_una_etiqueta_del_filtro(texto):
    """Cada `<` de la salida abre o cierra una etiqueta del filtro; el resto llega como
    `&lt;` (texto visible que no se ejecuta, aunque diga `src=` o `onerror=`)."""
    html = markdown_seguro(texto)

    for etiqueta in re.findall(r"<(/?[^\s>/]*)", html):
        assert etiqueta.lstrip("/") in PERMITIDAS, f"<{etiqueta}"
    assert "javascript:" not in "".join(re.findall(r'="([^"]*)"', html)).lower()


def test_los_enlaces_de_markdown_quedan_como_texto():
    html = markdown_seguro(
        "Consulta [el manual](https://senasica.gob.mx) y [esto](javascript:alert(1))."
    )

    assert "<a" not in html
    assert "[el manual](https://senasica.gob.mx)" in html
    assert "[esto](javascript:alert(1))" in html  # texto visible, sin efecto


def test_las_entidades_no_se_decodifican_dos_veces():
    html = markdown_seguro("&#60;script&#62;")

    assert "&amp;#60;script&amp;#62;" in html


def test_el_formato_sigue_funcionando_con_texto_hostil_alrededor():
    html = markdown_seguro("**Roña** <script>x</script>\n\n| a |\n|---|\n| **b** |")

    assert "<strong>Roña</strong>" in html and "<td><strong>b</strong></td>" in html
    assert_solo_lo_del_filtro(html)

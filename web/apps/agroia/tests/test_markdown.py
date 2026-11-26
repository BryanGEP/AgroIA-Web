"""markdown_seguro: formato de las respuestas del agente sin poder inyectar HTML."""

from apps.agroia.templatetags.markdown_seguro import markdown_seguro


def test_escapa_el_html_antes_de_dar_formato():
    html = markdown_seguro('<script>alert(1)</script> **hola** <img src=x onerror="robar()">')

    assert "<script>" not in html and "<img" not in html
    assert "&lt;script&gt;" in html and "&lt;img" in html
    assert "<strong>hola</strong>" in html


def test_negritas_cursivas_y_codigo():
    html = markdown_seguro("Usa **oxicloruro de cobre** y *revisa* la `dosis`.")

    assert "<strong>oxicloruro de cobre</strong>" in html
    assert "<em>revisa</em>" in html
    assert "<code" in html and ">dosis</code>" in html


def test_listas_y_encabezados():
    html = markdown_seguro("## Pasos\n1. Revisa la hoja\n2. Corta el fruto\n\n- Una\n- Otra")

    assert '<p class="font-bold">Pasos</p>' in html
    assert (
        '<ol class="list-decimal pl-5"><li>Revisa la hoja</li><li>Corta el fruto</li></ol>' in html
    )
    assert '<ul class="list-disc pl-5"><li>Una</li><li>Otra</li></ul>' in html


def test_tabla():
    html = markdown_seguro("| Rasgo | Roña |\n|---|---|\n| **Lesión** | Costra |")

    assert "<table" in html and "<th>Rasgo</th>" in html
    assert "<td><strong>Lesión</strong></td><td>Costra</td>" in html
    assert "|" not in html


def test_parrafos_y_saltos_de_linea():
    html = markdown_seguro("Primera línea\nsegunda línea\n\nOtro párrafo")

    assert "<p>Primera línea<br>segunda línea</p><p>Otro párrafo</p>" in html


def test_sin_estilos_en_linea():
    html = markdown_seguro("| a | b |\n|---|---|\n| 1 | 2 |\n\n**x** `y`")

    assert "style=" not in html

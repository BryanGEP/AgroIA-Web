"""Filtro `markdown_seguro`: muestra las respuestas del agente con formato, sin riesgo.

El agente responde en Markdown (negritas, listas, tablas). Primero se escapa TODO el HTML del
texto y después se convierte un subconjunto pequeño de Markdown a etiquetas fijas: una
respuesta nunca puede inyectar HTML, scripts ni atributos. No usa estilos en línea (CSP).

Soporta: párrafos, saltos de línea, encabezados (#, ##, ###), listas con viñetas (-, *) y
numeradas (1.), tablas con | y su fila separadora, **negritas**, *cursivas* y `código`.
"""

import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

NEGRITA = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
CURSIVA = re.compile(r"(?<![\*\w])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\*\w])")
CODIGO = re.compile(r"`([^`\n]+)`")
ENCABEZADO = re.compile(r"^(#{1,3})\s+(.*)$")
VINETA = re.compile(r"^\s*[-*]\s+(.*)$")
NUMERADA = re.compile(r"^\s*\d+[.)]\s+(.*)$")
SEPARADOR_DE_TABLA = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _en_linea(texto: str) -> str:
    """Formato dentro de una línea. Recibe texto ya escapado."""
    texto = CODIGO.sub(r'<code class="rounded bg-base-300 px-1">\1</code>', texto)
    texto = NEGRITA.sub(r"<strong>\1</strong>", texto)
    return CURSIVA.sub(r"<em>\1</em>", texto)


def _celdas(linea: str) -> list[str]:
    linea = linea.strip()
    if linea.startswith("|"):
        linea = linea[1:]
    if linea.endswith("|"):
        linea = linea[:-1]
    return [c.strip() for c in linea.split("|")]


def _tabla(filas: list[str]) -> str:
    encabezado, cuerpo = _celdas(filas[0]), [_celdas(f) for f in filas[2:]]
    html = ['<div class="overflow-x-auto my-2"><table class="table table-sm"><thead><tr>']
    html += [f"<th>{_en_linea(c)}</th>" for c in encabezado]
    html.append("</tr></thead><tbody>")
    for fila in cuerpo:
        html.append("<tr>" + "".join(f"<td>{_en_linea(c)}</td>" for c in fila) + "</tr>")
    html.append("</tbody></table></div>")
    return "".join(html)


@register.filter
def markdown_seguro(texto) -> str:
    lineas = escape(str(texto or "")).replace("\r\n", "\n").split("\n")
    bloques: list[str] = []
    parrafo: list[str] = []
    lista: tuple[str, list[str]] | None = None

    def cerrar_parrafo():
        if parrafo:
            bloques.append("<p>" + "<br>".join(_en_linea(p) for p in parrafo) + "</p>")
            parrafo.clear()

    def cerrar_lista():
        nonlocal lista
        if lista:
            etiqueta, elementos = lista
            clase = "list-decimal" if etiqueta == "ol" else "list-disc"
            items = "".join(f"<li>{_en_linea(e)}</li>" for e in elementos)
            bloques.append(f'<{etiqueta} class="{clase} pl-5">{items}</{etiqueta}>')
            lista = None

    i = 0
    while i < len(lineas):
        linea = lineas[i]
        # Tabla: una fila con |, seguida de la fila separadora |---|---|.
        if "|" in linea and i + 1 < len(lineas) and SEPARADOR_DE_TABLA.match(lineas[i + 1]):
            cerrar_parrafo()
            cerrar_lista()
            filas = [linea, lineas[i + 1]]
            i += 2
            while i < len(lineas) and "|" in lineas[i] and lineas[i].strip():
                filas.append(lineas[i])
                i += 1
            bloques.append(_tabla(filas))
            continue
        if not linea.strip():
            cerrar_parrafo()
            cerrar_lista()
        elif encabezado := ENCABEZADO.match(linea):
            cerrar_parrafo()
            cerrar_lista()
            bloques.append(f'<p class="font-bold">{_en_linea(encabezado.group(2))}</p>')
        elif (vineta := VINETA.match(linea)) or (numerada := NUMERADA.match(linea)):
            cerrar_parrafo()
            etiqueta = "ul" if vineta else "ol"
            if lista is None or lista[0] != etiqueta:
                cerrar_lista()
                lista = (etiqueta, [])
            lista[1].append((vineta or numerada).group(1))
        else:
            cerrar_lista()
            parrafo.append(linea)
        i += 1
    cerrar_parrafo()
    cerrar_lista()
    return mark_safe('<div class="flex flex-col gap-2">' + "".join(bloques) + "</div>")

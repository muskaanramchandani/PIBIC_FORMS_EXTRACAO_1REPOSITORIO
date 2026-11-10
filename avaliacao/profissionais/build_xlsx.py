"""
Gera a planilha dos coautores, no formato do template.

Uso: python3 build_xlsx.py <pasta de sistemas> <saída.xlsx> [sistema a excluir ...]

Cada sistema tem o `detections.json` em `<sistema>/` ou `<sistema>/artefatos/`. A
primeira aba é o "Sobre você"; depois, uma aba por sistema, com as
linhas na mesma ordem e no mesmo agrupamento da página do DAMFE: as
detecções de rota do mesmo anti-padrão viram uma linha só.
"""

import csv
import json
import sys

import build_sheet
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation


FONT = "Comfortaa"
HEADER = dict(
    font=Font(name=FONT, size=12, bold=True, color="FFFFFFFF"),
    fill=PatternFill("solid", fgColor="FF3D85C6"),
    alignment=Alignment(horizontal="center", vertical="center", wrap_text=True),
)

#: Larguras do template (avaliacao-Bahmni.xlsx).
WIDTHS = {"A": 4.13, "B": 19.88, "C": 24.63, "D": 30.25, "E": 21.5, "F": 20.75}

#: Seções do "Sobre você", em negrito.
SECTIONS = {"VOCÊ", "ANTI-PADRÕES"}


def read(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.reader(handle))


def style_header(sheet, columns: int) -> None:
    for cell in sheet[1][:columns]:
        for name, value in HEADER.items():
            setattr(cell, name, value)


def cell(sheet, row: int, column: int, value, horizontal: str = "left", bold: bool = False) -> None:
    target = sheet.cell(row=row, column=column, value=value)
    target.font = Font(name=FONT, bold=bold)
    target.alignment = Alignment(horizontal=horizontal, vertical="center", wrap_text=True)


def dropdown(sheet, options: str, cells: list[str]) -> None:
    if not cells:
        return
    validation = DataValidation(type="list", formula1=f'"{options}"', allow_blank=True)
    for coordinate in cells:
        validation.add(coordinate)
    sheet.add_data_validation(validation)


def about(book: Workbook, rows: list[list[str]]) -> None:

    sheet = book.active
    sheet.title = "Sobre você"
    answers = []

    for number, (question, answer) in enumerate(rows, 1):
        if number == 1:
            sheet.append([question, answer])
            continue
        cell(sheet, number, 1, question, bold=question in SECTIONS)
        cell(sheet, number, 2, answer or None)
        if "(sim/não/não sei)" in question:
            answers.append(f"B{number}")

    style_header(sheet, 2)
    dropdown(sheet, "Sim,Não,Não sei", answers)
    sheet.column_dimensions["A"].width = 60
    sheet.column_dimensions["B"].width = 40


HEADER_ROW = ["#", "anti-padrão", "micro frontends", "endpoint",
              "julgamento (Sim/Não/Não sei)", "justificativa (se Não ou Não sei)"]


def short(name: str) -> str:
    return name.rpartition("/")[2] or name


def groups(detections: list[dict]) -> list[list[dict]]:
    """Como `_detections` da página (visualization/html.py)."""

    detections = sorted(detections, key=lambda item: (item["anti_pattern"], item["dimension"], item["message"]))
    found: list[list[dict]] = []
    routes: dict[str, list[dict]] = {}

    for item in detections:
        if not (item.get("metadata") or {}).get("path"):
            found.append([item])
        elif item["anti_pattern"] in routes:
            routes[item["anti_pattern"]].append(item)
        else:
            routes[item["anti_pattern"]] = [item]
            found.append(routes[item["anti_pattern"]])

    return found


def line(group: list[dict]) -> list[str]:

    subjects = sorted({short(subject) for item in group for subject in item.get("subjects") or []})
    paths = [item["metadata"]["path"] for item in group if (item.get("metadata") or {}).get("path")]
    endpoint = f"{len(paths)} rotas:\n" + "\n".join(paths) if len(paths) > 1 else "".join(paths)

    return [group[0]["anti_pattern"], ", ".join(subjects), endpoint]


def reference(group: list[dict]) -> str:
    """O link da definição do anti-padrão no catálogo, que o DAMFE grava na detecção."""
    return group[0].get("reference") or ""


def system(book: Workbook, name: str, rows: list[list], links: list[str]) -> None:

    sheet = book.create_sheet(name[:31])
    sheet.append(HEADER_ROW)
    style_header(sheet, len(HEADER_ROW))

    for number, row in enumerate(rows, 2):
        for column, value in enumerate(row, 1):
            if column == 1:
                cell(sheet, number, column, value, horizontal="center")
            else:
                cell(sheet, number, column, value or None)

    # O nome do anti-padrão leva à definição no catálogo, para quem
    # não o conhece.
    for number, link in enumerate(links, 2):
        if link:
            target = sheet.cell(row=number, column=2)
            target.hyperlink = link
            target.font = Font(name=FONT, color="FF1155CC", underline="single")

    dropdown(sheet, "Sim,Não,Não sei", [f"E{number}" for number in range(2, len(rows) + 2)])
    for column, width in WIDTHS.items():
        sheet.column_dimensions[column].width = width


def main(root: str, output: str, *excluded: str) -> None:

    book = Workbook()
    # As perguntas do "Sobre você" são as de `build_sheet.py`.
    about(book, build_sheet.about())

    def detections_of(path: Path) -> Path | None:
        for candidate in (path / "detections.json", path / "artefatos" / "detections.json"):
            if candidate.is_file():
                return candidate
        return None

    systems = sorted(
        (path for path in Path(root).iterdir() if path.is_dir() and detections_of(path) and path.name not in excluded),
        key=lambda path: path.name.lower(),
    )

    # O `#` é da planilha inteira: a análise junta as abas.
    number = 0
    for path in systems:
        rows, links = [], []
        for group in groups(json.loads(detections_of(path).read_text())):
            number += 1
            rows.append([number, *line(group), "", ""])
            links.append(reference(group))
        if rows:
            system(book, path.name, rows, links)

    book.save(output)
    print(f"{number} itens em {len(book.sheetnames) - 1} abas → {output}")


if __name__ == "__main__":
    main(*sys.argv[1:])

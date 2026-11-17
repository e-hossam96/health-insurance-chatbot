from __future__ import annotations

import argparse
import io
import textwrap
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "packages" / "chatbot_ai" / "src" / "chatbot_ai" / "evals" / "kb_fixtures"

PAGE_WIDTH, PAGE_HEIGHT, MARGIN = 612, 792, 54
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ZIP_CREATE_SYSTEM_UNIX = 3


@dataclass(frozen=True)
class Heading:
    level: int
    text: str


@dataclass(frozen=True)
class Paragraph:
    text: str


@dataclass(frozen=True)
class Table:
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


Block = Heading | Paragraph | Table


@dataclass(frozen=True)
class FixtureDocument:
    file_name: str
    title: str
    blocks: tuple[Block, ...]


CLINICS = ("Cairo Clinic", "Nile Medical", "Giza Care", "Delta Health", "Alexandria Point", "Heliopolis Center")
SERVICES = ("General consultation", "Specialist consultation", "Blood test panel", "X-ray", "Ultrasound", "Physiotherapy session", "ECG", "Vaccination", "Dental cleaning", "Eye exam")


def _fee_schedule_rows() -> tuple[tuple[str, ...], ...]:
    rows: list[tuple[str, ...]] = []
    for index in range(60):
        clinic = CLINICS[index % len(CLINICS)]
        service = SERVICES[index % len(SERVICES)]
        fee = 150 + (index * 37) % 900
        copay = 10 + (index * 7) % 40
        rows.append((clinic, service, f"{fee} EGP", f"{copay}%"))
    return tuple(rows)


def _dental_vision_rows() -> tuple[tuple[str, ...], ...]:
    items = ("Routine cleaning", "Filling", "Root canal", "Crown", "Extraction", "Eye exam", "Glasses lenses", "Glasses frames", "Contact lenses")
    rows: list[tuple[str, ...]] = []
    for index in range(45):
        item = items[index % len(items)]
        tier = ("Basic", "Plus", "Premium")[index % 3]
        limit = 500 + (index * 113) % 4000
        rows.append((tier, item, f"{limit} EGP per year", "Yes" if index % 4 else "No"))
    return tuple(rows)


POLICY_HANDBOOK = FixtureDocument(
    file_name="policy_handbook.pdf",
    title="Health Plan Policy Handbook",
    blocks=(
        Heading(1, "1 Overview"),
        Paragraph(
            "This handbook describes the benefits of the Health Plan for members and their dependents. "
            "Coverage starts on the first day of the month after enrollment and renews every January 1."
        ),
        Paragraph("All amounts are in Egyptian pounds (EGP). All times are UTC."),
        Heading(1, "2 Covered services"),
        Heading(2, "2.1 Outpatient care"),
        Paragraph(
            "Outpatient visits at network clinics have a co-pay of 50 EGP per visit. "
            "Specialist visits need no referral. Telemedicine consultations are covered at no co-pay."
        ),
        Heading(2, "2.2 Inpatient care"),
        Paragraph(
            "Hospital stays are covered up to 30 nights per year in a semi-private room. "
            "Planned admissions require pre-authorization at least 5 working days in advance."
        ),
        Heading(2, "2.3 Annual coverage limits"),
        Table(
            header=("Benefit", "Annual limit", "Co-pay"),
            rows=(
                ("Outpatient visits", "Unlimited", "50 EGP"),
                ("Inpatient stay", "30 nights", "0 EGP"),
                ("Prescription drugs", "20000 EGP", "10%"),
                ("Maternity", "35000 EGP", "0 EGP"),
                ("Physiotherapy", "24 sessions", "20%"),
            ),
        ),
        Heading(1, "3 Exclusions"),
        Paragraph(
            "The plan does not cover cosmetic surgery, experimental treatments, or treatment received outside the network "
            "except in an emergency. Injuries from professional sports are excluded."
        ),
        Heading(1, "4 Claims"),
        Heading(2, "4.1 Submitting a claim"),
        Paragraph("Submit reimbursement claims within 90 days of the service date with the original receipts and the medical report."),
        Heading(2, "4.2 Appeals"),
        Paragraph("A rejected claim can be appealed once, in writing, within 30 days of the decision. Appeals are answered within 15 working days."),
        Heading(1, "5 Network clinic fee schedule"),
        Paragraph("The table lists the negotiated fee and the member co-pay for common services at each network clinic."),
        Table(header=("Clinic", "Service", "Fee", "Member co-pay"), rows=_fee_schedule_rows()),
    ),
)

MEMBER_GUIDE = FixtureDocument(
    file_name="member_guide.docx",
    title="Member Guide",
    blocks=(
        Heading(1, "Getting started"),
        Paragraph("Your member card arrives within 10 days of enrollment. Show it at every network clinic visit."),
        Heading(1, "Booking visits"),
        Paragraph(
            "Book visits through the chat assistant or the member portal. You can cancel a scheduled visit up to its start time. "
            "Missed visits without cancellation are counted, and three missed visits in a year suspend online booking for 30 days."
        ),
        Heading(1, "Complaints"),
        Paragraph("You can file one complaint per completed visit. The care team replies within 3 working days."),
        Heading(1, "Pre-authorization"),
        Heading(2, "Services that need approval"),
        Table(
            header=("Service", "Approval needed", "Lead time"),
            rows=(
                ("MRI scan", "Yes", "3 working days"),
                ("CT scan", "Yes", "3 working days"),
                ("Planned surgery", "Yes", "5 working days"),
                ("Blood tests", "No", "None"),
            ),
        ),
        Heading(1, "Dental and vision benefits"),
        Heading(2, "Benefit tiers"),
        Paragraph("Dental and vision benefits depend on the plan tier. The table lists the yearly limit per item."),
        Table(header=("Tier", "Item", "Yearly limit", "Needs approval"), rows=_dental_vision_rows()),
    ),
)


def _pdf_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class _PdfLayout:
    def __init__(self) -> None:
        self.pages: list[list[str]] = []
        self.y = 0.0
        self._new_page()

    def _new_page(self) -> None:
        self.pages.append([])
        self.y = PAGE_HEIGHT - MARGIN

    def _ensure(self, height: float) -> bool:
        if self.y - height < MARGIN:
            self._new_page()
            return True
        return False

    def text(self, text: str, size: float, bold: bool = False, x: float = MARGIN) -> None:
        font = "F2" if bold else "F1"
        self.pages[-1].append(f"BT /{font} {size:g} Tf {x:.1f} {self.y:.1f} Td ({_pdf_string(text)}) Tj ET")

    def heading(self, heading: Heading) -> None:
        size = 16 if heading.level == 1 else 13
        self._ensure(size * 2.4)
        self.y -= size * 1.2
        self.text(heading.text, size, bold=True)
        self.y -= size * 0.6

    def paragraph(self, paragraph: Paragraph) -> None:
        size = 10.0
        for line in textwrap.wrap(paragraph.text, width=int(CONTENT_WIDTH / (size * 0.5))):
            self._ensure(size * 1.4)
            self.y -= size * 1.4
            self.text(line, size)
        self.y -= size * 0.8

    def _table_row(self, cells: tuple[str, ...], bold: bool, row_height: float, column_width: float) -> None:
        bottom = self.y - row_height
        for index, cell in enumerate(cells):
            x = MARGIN + index * column_width
            self.pages[-1].append(f"{x:.1f} {bottom:.1f} {column_width:.1f} {row_height:.1f} re S")
            saved = self.y
            self.y = bottom + 4
            self.text(cell, 8, bold=bold, x=x + 3)
            self.y = saved
        self.y = bottom

    def table(self, table: Table) -> None:
        row_height = 14.0
        column_width = CONTENT_WIDTH / len(table.header)
        self._ensure(row_height * 3)
        self.y -= 4
        self._table_row(table.header, True, row_height, column_width)
        for row in table.rows:
            if self._ensure(row_height):
                self._table_row(table.header, True, row_height, column_width)
            self._table_row(row, False, row_height, column_width)
        self.y -= 10


def _pdf_bytes(page_streams: list[str]) -> bytes:
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    page_ids: list[int] = []
    for stream in page_streams:
        content = stream.encode("latin-1")
        objects.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        content_id = len(objects)
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode("ascii")
        )
        page_ids.append(len(objects))
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n")
    xref_at = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii"))
    return out.getvalue()


def render_pdf(document: FixtureDocument) -> bytes:
    layout = _PdfLayout()
    layout.heading(Heading(1, document.title))
    for block in document.blocks:
        if isinstance(block, Heading):
            layout.heading(block)
        elif isinstance(block, Paragraph):
            layout.paragraph(block)
        else:
            layout.table(block)
    return _pdf_bytes(["\n".join(page) for page in layout.pages])


def render_scanned_pdf() -> bytes:
    shapes = [f"{MARGIN + i * 40} {PAGE_HEIGHT - 200 - i * 30} 300 12 re f" for i in range(12)]
    return _pdf_bytes(["0.3 g\n" + "\n".join(shapes)])


def _docx_paragraph(text: str, style: str | None = None) -> str:
    properties = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{properties}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def _docx_table(table: Table) -> str:
    def row(cells: tuple[str, ...], header: bool) -> str:
        row_properties = "<w:trPr><w:tblHeader/></w:trPr>" if header else ""
        cell_xml = "".join(f"<w:tc>{_docx_paragraph(cell)}</w:tc>" for cell in cells)
        return f"<w:tr>{row_properties}{cell_xml}</w:tr>"

    grid = "".join('<w:gridCol w:w="2000"/>' for _ in table.header)
    rows = row(table.header, True) + "".join(row(r, False) for r in table.rows)
    return f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/></w:tblPr><w:tblGrid>{grid}</w:tblGrid>{rows}</w:tbl>'


DOCX_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    "</Types>"
)
DOCX_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    "</Relationships>"
)
DOCX_DOCUMENT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)


def _docx_style(style_id: str, name: str, kind: str = "paragraph", extra: str = "", default: bool = False) -> str:
    default_attr = ' w:default="1"' if default else ""
    return f'<w:style w:type="{kind}"{default_attr} w:styleId="{style_id}"><w:name w:val="{name}"/>{extra}</w:style>'


DOCX_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    + _docx_style("Normal", "Normal", default=True)
    + _docx_style("Title", "Title", extra='<w:basedOn w:val="Normal"/>')
    + _docx_style("Heading1", "heading 1", extra='<w:basedOn w:val="Normal"/><w:pPr><w:outlineLvl w:val="0"/></w:pPr>')
    + _docx_style("Heading2", "heading 2", extra='<w:basedOn w:val="Normal"/><w:pPr><w:outlineLvl w:val="1"/></w:pPr>')
    + _docx_style("TableGrid", "Table Grid", kind="table")
    + "</w:styles>"
)


def render_docx(document: FixtureDocument) -> bytes:
    body = [_docx_paragraph(document.title, "Title")]
    for block in document.blocks:
        if isinstance(block, Heading):
            body.append(_docx_paragraph(block.text, f"Heading{block.level}"))
        elif isinstance(block, Paragraph):
            body.append(_docx_paragraph(block.text))
        else:
            body.append(_docx_table(block))
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        + "".join(body)
        + "<w:sectPr/></w:body></w:document>"
    )
    parts = [
        ("[Content_Types].xml", DOCX_CONTENT_TYPES),
        ("_rels/.rels", DOCX_ROOT_RELS),
        ("word/_rels/document.xml.rels", DOCX_DOCUMENT_RELS),
        ("word/document.xml", document_xml),
        ("word/styles.xml", DOCX_STYLES),
    ]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, content in parts:
            info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
            info.create_system = ZIP_CREATE_SYSTEM_UNIX
            # stored, not deflated: zlib output differs between the Windows and Linux Python builds
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content.encode("utf-8"))
    return out.getvalue()


def render_all() -> dict[str, bytes]:
    return {
        POLICY_HANDBOOK.file_name: render_pdf(POLICY_HANDBOOK),
        MEMBER_GUIDE.file_name: render_docx(MEMBER_GUIDE),
        "scanned_notice.pdf": render_scanned_pdf(),
    }


def write_fixtures(output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, content in render_all().items():
        path = output / name
        path.write_bytes(content)
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the synthetic KB fixtures")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    for path in write_fixtures(args.output):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Bounded CSV/XLSX readers. Parsing has no network access or formula engine."""

from contextlib import closing
import csv
from dataclasses import dataclass
from datetime import date, datetime, time
from io import BytesIO, StringIO
from pathlib import PurePosixPath
import re
from xml.parsers import expat
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile
from zlib import error as CompressionError

from openpyxl import load_workbook
from openpyxl.utils.cell import column_index_from_string
from openpyxl.utils.exceptions import InvalidFileException


MAX_UPLOAD = 8 * 1024 * 1024
MAX_ROWS = 5000
MAX_COLUMNS = 64
MAX_CELL = 32767
MAX_TEXT = 12 * 1024 * 1024
MAX_XLSX_EXPANDED = 48 * 1024 * 1024
MAX_SHEETS = 40


class ImportProblem(ValueError):
    pass


@dataclass(frozen=True)
class FileRow:
    line: int
    values: list[str]
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class Sheet:
    name: str
    header_line: int
    columns: list[str]
    rows: list[FileRow]
    encoding: str | None = None
    delimiter: str | None = None


def file_kind(name):
    if not name or len(name) > 240 or name in {".", ".."} or re.search(r'[\\/:*?"<>|\x00-\x1f\x7f]', name):
        raise ImportProblem("文件名无效，请使用不含路径的原文件名。")
    ext = PurePosixPath(name).suffix.lower()
    if ext not in {".csv", ".xlsx"}:
        raise ImportProblem("请选择 CSV 或 XLSX 文件。")
    return ext[1:]


def as_sheet(name, rows, encoding=None, delimiter=None):
    columns = None
    result = []
    total = 0
    for row in rows:
        values = row.values
        if not values or columns is None and not any(values) and not row.errors:
            continue
        if len(values) > MAX_COLUMNS:
            raise ImportProblem(f"单行最多支持 {MAX_COLUMNS} 列。")
        if any(len(cell) > MAX_CELL for cell in values):
            raise ImportProblem(f"第 {row.line} 行包含过长的单元格。")
        total += sum(len(cell.encode("utf-8")) for cell in values)
        if total > MAX_TEXT:
            raise ImportProblem("解码后的文本太大，请拆分文件或精简工作表。")
        if columns is None:
            if row.errors or not any(value.strip() for value in values):
                raise ImportProblem("首个非空行必须是可读取的表头。")
            columns = values
            header_line = row.line
            continue
        if len(result) >= MAX_ROWS:
            raise ImportProblem(f"单个工作表最多导入 {MAX_ROWS} 条记录。")
        if len(values) != len(columns):
            row = FileRow(row.line, values, (*row.errors, "row_width"))
        result.append(row)
    if columns is None or not result:
        raise ImportProblem("没有可导入的数据。请在首个非空行填写表头，并至少提供一条记录。")
    return Sheet(name, header_line, columns, result, encoding, delimiter)


def read_csv(data):
    for codec, label in (("utf-8-sig", "UTF-8 BOM" if data.startswith(b"\xef\xbb\xbf") else "UTF-8"),
                         ("gb18030", "GB18030")):
        try:
            decoded = data.decode(codec)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ImportProblem("无法识别 CSV 编码，请另存为 UTF-8 或 GB18030。")
    if "\x00" in decoded or any(ord(c) < 32 and c not in "\t\r\n" for c in decoded):
        raise ImportProblem("CSV 含二进制或不支持的控制字符。")

    # The header, not malformed data rows, determines the delimiter.
    def width(separator):
        try:
            head = next((row for row in csv.reader(StringIO(decoded, newline=""), delimiter=separator, strict=True)
                         if any(row)), [])
            return len(head)
        except csv.Error:
            return 0

    separators = (",", "\t", ";", "|")
    delimiter = max(separators, key=width)
    reader = csv.reader(StringIO(decoded, newline=""), delimiter=delimiter, strict=True)

    def rows():
        while True:
            line = reader.line_num + 1
            try:
                yield FileRow(line, next(reader))
            except StopIteration:
                return
            except csv.Error:
                raise ImportProblem(f"CSV 第 {line} 行的引号或字段格式无法解析。") from None

    return as_sheet("CSV", rows(), label, delimiter)


def inspect_xml(archive, item):
    parser = expat.ParserCreate(namespace_separator=" ")
    depth = nodes = 0
    worksheet = False

    def forbidden(*_):
        raise ImportProblem("Excel 含不支持的 XML 声明。")

    def start(tag, attributes):
        nonlocal depth, nodes, worksheet
        depth += 1
        nodes += 1
        local = tag.rsplit(" ", 1)[-1]
        if depth == 1:
            worksheet = local == "worksheet"
        if depth > 64 or nodes > 500_000:
            raise ImportProblem("Excel 文件结构过于复杂，请拆分后重试。")
        # Ensure that parts the read-only workbook parser follows are among
        # the XML parts inspected here, regardless of package-supplied names.
        if local == "Relationship" and attributes.get("Type", "").rsplit("/", 1)[-1] in {
            "officeDocument", "worksheet", "chartsheet", "sharedStrings", "styles",
        }:
            target = attributes.get("Target", "")
            if (attributes.get("TargetMode") == "External" or ":" in target
                    or not target.lower().endswith(".xml")):
                raise ImportProblem("Excel 工作表关系指向不受支持的文件。")
        if local == "Override" and attributes.get("ContentType", "").lower().endswith(("worksheet+xml", "sharedstrings+xml")):
            if not attributes.get("PartName", "").lower().endswith(".xml"):
                raise ImportProblem("Excel 工作表部件格式无效。")
        if worksheet and local == "row" and "r" in attributes:
            if int(attributes["r"]) not in range(1, MAX_ROWS + 2):
                raise ImportProblem(f"Excel 行号最多支持 {MAX_ROWS + 1}，包括表头。")
        if worksheet and local == "c" and "r" in attributes:
            coord = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", attributes["r"])
            if not coord or column_index_from_string(coord[1]) > MAX_COLUMNS or int(coord[2]) > MAX_ROWS + 1:
                raise ImportProblem("Excel 单元格超出允许的行列范围。")

    def end(_):
        nonlocal depth
        depth -= 1

    parser.StartDoctypeDeclHandler = forbidden
    parser.EntityDeclHandler = forbidden
    parser.ExternalEntityRefHandler = forbidden
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    with archive.open(item) as stream:
        while chunk := stream.read(65536):
            parser.Parse(chunk, False)
        parser.Parse(b"", True)


def inspect_xlsx(data):
    with ZipFile(BytesIO(data)) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(entries) > 384 or sum(entry.file_size for entry in entries) > MAX_XLSX_EXPANDED:
            raise ImportProblem("Excel 解压后的体积或文件数量超限。")
        if len(set(names)) != len(names) or "[Content_Types].xml" not in names:
            raise ImportProblem("Excel 文件结构无效。")
        for item in entries:
            name = item.filename
            path = PurePosixPath(name)
            if (path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name
                    or item.flag_bits & 1 or item.compress_type not in (ZIP_STORED, ZIP_DEFLATED)):
                raise ImportProblem("Excel 包含不安全或不受支持的压缩条目。")
            if "vbaproject" in name.lower() or name.lower().startswith("xl/embeddings/"):
                raise ImportProblem("请选择不含宏或嵌入文件的 XLSX。")
            if name.lower().endswith((".xml", ".rels")):
                inspect_xml(archive, item)


def cell_text(value):
    if value is None:
        return ""
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def workbook_data(data, index=None):
    try:
        inspect_xlsx(data)
        with closing(load_workbook(BytesIO(data), read_only=True, data_only=False, keep_links=False)) as book:
            sheets = book.worksheets
            if not 0 < len(sheets) <= MAX_SHEETS:
                raise ImportProblem(f"工作簿须包含 1 到 {MAX_SHEETS} 张工作表。")
            if index is None:
                return [s.title for s in sheets]
            if not 0 <= index < len(sheets):
                raise ImportProblem("所选工作表不存在。")
            sheet = sheets[index]
            sheet.reset_dimensions()

            def rows():
                header_width = 0
                for line, cells in enumerate(sheet.iter_rows(max_col=MAX_COLUMNS + 1), 1):
                    if line > MAX_ROWS + 1:
                        raise ImportProblem(f"Excel 行号最多支持 {MAX_ROWS + 1}，包括表头。")
                    values = [cell_text(c.value) for c in cells]
                    width = next((i for i in range(len(values), 0, -1) if values[i - 1]), 0)
                    if not width:
                        continue
                    if not header_width:
                        header_width = width
                    errors = ()
                    if any(c.data_type == "f" for c in cells):
                        errors += ("excel_formula",)
                    if any(c.data_type == "e" for c in cells):
                        errors += ("excel_cell_error",)
                    yield FileRow(line, values[:max(width, header_width)], errors)

            return as_sheet(sheet.title, rows())
    except ImportProblem:
        raise
    except (BadZipFile, expat.ExpatError, ValueError, TypeError, KeyError, IndexError, OSError,
            OverflowError, AttributeError, EOFError, SyntaxError, RuntimeError, CompressionError, InvalidFileException):
        raise ImportProblem("无法读取 XLSX。文件可能损坏、加密或格式不受支持。") from None


def list_sheets(data, kind):
    if kind == "csv":
        read_csv(data)
        return ["CSV"]
    return workbook_data(data)


def read_sheet(data, kind, index):
    if kind == "csv":
        if index != 0:
            raise ImportProblem("CSV 只有一张表。")
        return read_csv(data)
    return workbook_data(data, index)

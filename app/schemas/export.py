from enum import Enum


class ExportFormat(str, Enum):
    TXT = "txt"
    MD = "md"
    DOCX = "docx"
    PDF = "pdf"

from app.models import Document


class DocumentRepository:
    def __init__(self) -> None:
        self._documents: dict[str, Document] = {}

    def add(self, document: Document) -> None:
        self._documents[document.id] = document

    def fetch(self, document_id: str, organization_id: str) -> Document | None:
        document = self._documents.get(document_id)
        if document is None or document.organization_id != organization_id:
            return None
        return document

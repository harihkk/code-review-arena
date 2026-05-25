DOCUMENT_LOOKUP_SQL = """
SELECT d.id, d.title
FROM documents d
JOIN projects p ON p.id = d.project_id
WHERE d.id = :document_id
"""

from app.db import DocumentRepository
from app.models import Document, User


def get_document_for_user(
    repo: DocumentRepository, document_id: str, user: User
) -> Document | None:
    return repo.fetch(document_id)

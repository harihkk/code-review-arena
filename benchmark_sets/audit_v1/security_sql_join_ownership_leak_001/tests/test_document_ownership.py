from app.db import DocumentRepository
from app.documents import get_document_for_user
from app.models import Document, User


def test_cross_organization_document_access_is_denied():
    repo = DocumentRepository()
    repo.add(Document(id="doc-1", organization_id="org_a", title="Secret plan"))
    org_b_user = User(id="user-b", organization_id="org_b")
    assert get_document_for_user(repo, "doc-1", org_b_user) is None

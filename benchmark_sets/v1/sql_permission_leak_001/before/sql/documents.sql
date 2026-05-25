SELECT id, title, body
FROM documents
WHERE id = :document_id
  AND organization_id = :organization_id;


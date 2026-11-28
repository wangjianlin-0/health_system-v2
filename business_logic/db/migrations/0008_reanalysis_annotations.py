"""Backfill missing user annotations on records created by reanalysis."""
VERSION = 8
NAME = "reanalysis_annotations"


def apply(db):
    db.execute("""UPDATE records AS child
        SET note = (SELECT source.note FROM records AS source
                    WHERE source.id = child.supersedes_record_id AND source.owner_id = child.owner_id)
        WHERE child.supersedes_record_id IS NOT NULL AND child.note IS NULL
          AND EXISTS (SELECT 1 FROM records AS source WHERE source.id = child.supersedes_record_id
                      AND source.owner_id = child.owner_id AND source.note IS NOT NULL)""")
    db.execute("""UPDATE records AS child
        SET payload = json_set(child.payload, '$.note', child.note)
        WHERE child.supersedes_record_id IS NOT NULL AND child.note IS NOT NULL
          AND json_extract(child.payload, '$.note') IS NULL""")
    db.execute("""UPDATE records AS child
        SET payload = json_set(child.payload, '$.body_context',
            json((SELECT json_extract(source.payload, '$.body_context')
                  FROM records AS source WHERE source.id = child.supersedes_record_id
                    AND source.owner_id = child.owner_id)))
        WHERE child.supersedes_record_id IS NOT NULL
          AND json_extract(child.payload, '$.body_context') IS NULL
          AND EXISTS (SELECT 1 FROM records AS source WHERE source.id = child.supersedes_record_id
                      AND source.owner_id = child.owner_id
                      AND json_extract(source.payload, '$.body_context') IS NOT NULL)""")

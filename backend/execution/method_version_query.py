"""Bounded keyset selection for immutable Product Method versions."""
from contracts.primitives import require


def version_rows(db, workspace_id, family_id, *, after_version, limit):
    require(type(after_version) is int and after_version >= 0 and
            type(limit) is int and 1 <= limit <= 50,
            'methodVersionPage', 'INVALID_INPUT')
    rows=db.execute(
        'SELECT v.version,v.method_id,m.payload,m.content_hash '
        'FROM btl.product_method_versions v JOIN btl.tick_methods m '
        'ON m.workspace_id=v.workspace_id AND m.method_id=v.method_id '
        'WHERE v.workspace_id=%s AND v.family_id=%s AND v.version>%s '
        'ORDER BY v.version LIMIT %s',
        (workspace_id,family_id,after_version,limit+1)).fetchall()
    page=rows[:limit]
    expected=after_version+1
    for row in page:
        require(row['version']==expected,'methodVersion','CORRUPT_RECORD')
        expected+=1
    return page,len(rows)>limit


def latest_version_window(db, workspace_id, family_id, *, latest_version, limit):
    """Return a bounded compatibility window ending at the current version."""
    require(type(latest_version) is int and latest_version >= 1 and
            type(limit) is int and 1 <= limit <= 128,
            'methodVersionWindow', 'INVALID_INPUT')
    rows=db.execute(
        'SELECT v.version,v.method_id,m.payload,m.content_hash '
        'FROM btl.product_method_versions v JOIN btl.tick_methods m '
        'ON m.workspace_id=v.workspace_id AND m.method_id=v.method_id '
        'WHERE v.workspace_id=%s AND v.family_id=%s AND v.version<=%s '
        'ORDER BY v.version DESC LIMIT %s',
        (workspace_id,family_id,latest_version,limit+1)).fetchall()
    window=list(reversed(rows[:limit]))
    first_version=max(1,latest_version-limit+1)
    expected=first_version
    for row in window:
        require(row['version']==expected,'methodVersion','CORRUPT_RECORD')
        expected+=1
    require(expected==latest_version+1 and
            (not rows or rows[0]['version']==latest_version),
            'methodVersion','CORRUPT_RECORD')
    return window,latest_version>limit

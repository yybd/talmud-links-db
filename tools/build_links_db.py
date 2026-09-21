#!/usr/bin/env python3
"""בניית links.db — גרף הקישורים של הש"ס, מחולץ ממסד אוצריא.

הקלט הוא seforim.db של אוצריא (7.9GB), והפלט הוא מסד של ~350MB שמחזיק
את הגרף בלבד: מי מדבר על כל שורה, ואיפה. הטקסט עצמו אינו מועתק — הוא
מה שתופס 4.7GB מתוך המקור, וכאן הוא מיותר: הקישור הוא הצבעה, ואת
הטקסט מספקים שרתי ה-MCP.

    python3 tools/build_links_db.py [--src PATH] [--out PATH]

ברירת המחדל לקלט היא ההתקנה של אוצריא במק; ב-CI מעבירים ‎--src אל
‎seforim.db שהורד מהריליס של אוצריא. הפלט **אינו נכנס לגיט** — הוא
ארטיפקט, ו-.gitignore חוסם את build/.
"""
import argparse, os, sqlite3, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dh_match import norm, tight

DEFAULT_SRC = os.path.expanduser(
    '~/Library/Application Support/otzaria/books/seforim.db')
DEFAULT_OUT = 'build/links.db'

# 36 מסכתות הבבלי כפי שהן נקראות ב-book.title במסד, וכפי שהן מגיעות
# מ-ai-bridge ב-masechetName. השמות זהים בשני הצדדים — נבדק.
MASECHTOT = [
    'ברכות', 'שבת', 'עירובין', 'פסחים', 'ראש השנה', 'יומא', 'סוכה', 'ביצה',
    'תענית', 'מגילה', 'מועד קטן', 'חגיגה', 'יבמות', 'כתובות', 'נדרים', 'נזיר',
    'סוטה', 'גיטין', 'קידושין', 'בבא קמא', 'בבא מציעא', 'בבא בתרא', 'סנהדרין',
    'מכות', 'שבועות', 'עבודה זרה', 'הוריות', 'זבחים', 'מנחות', 'חולין',
    'בכורות', 'ערכין', 'תמורה', 'כריתות', 'מעילה', 'נדה',
]


def log(msg, t0=[time.time()]):
    print(f'[{time.time() - t0[0]:6.1f}s] {msg}', flush=True)


def build(src, out):
    if not os.path.exists(src):
        sys.exit(f'לא נמצא מסד המקור: {src}\n'
                 'התקן את אוצריא ומשוך את הספרייה, או העבר --src.')
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    if os.path.exists(out):
        os.remove(out)

    db = sqlite3.connect(out)
    db.executescript('PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;')
    db.execute("ATTACH ? AS s", (f'file:{src}?immutable=1',))
    # ‏sqlite3 של פייתון לא מכבד uri= ב-ATTACH דרך הפרמטר; פותחים מחדש נכון
    db.close()
    db = sqlite3.connect(out)
    db.executescript('PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;')
    db.execute(f"ATTACH 'file:{src}?immutable=1' AS s")

    log('book / connection_type')
    db.executescript("""
        CREATE TABLE book AS SELECT id, title FROM s.book;
        CREATE TABLE connection_type AS SELECT id, name FROM s.connection_type;
    """)

    log('daf_line — פירוק heRef של הבבלי לדף ולעמוד')
    # ‏heRef של הבבלי הוא בדיוק "ברכות, ב., א" — מסכת, דף+עמוד, שורה.
    # זה אותו צירוף ש-ai-bridge שולח (masechetName + dafLabel), ולכן
    # החיפוש כאן הוא שוויון על אינדקס ולא LIKE.
    qs = ','.join('?' * len(MASECHTOT))
    db.execute(f"""
        CREATE TABLE daf_line AS
        SELECT b.title AS masechet,
               TRIM(SUBSTR(l.heRef, LENGTH(b.title) + 3,
                    INSTR(SUBSTR(l.heRef, LENGTH(b.title) + 3), ',') - 1)) AS daf,
               l.lineIndex AS lineIndex,
               l.id        AS lineId
        FROM s.line l JOIN s.book b ON b.id = l.bookId
        WHERE b.title IN ({qs}) AND l.heRef LIKE b.title || ', %'
    """, MASECHTOT)
    n = db.execute('SELECT COUNT(*) FROM daf_line').fetchone()[0]
    log(f'  {n:,} שורות גמרא')

    log('link — רק קישורים שנוגעים בבבלי')
    db.executescript("""
        CREATE TEMP TABLE daf_ids AS SELECT lineId AS id FROM daf_line;
        CREATE UNIQUE INDEX tmp_daf_ids ON daf_ids(id);
        CREATE TABLE link AS
        SELECT l.sourceLineId, l.targetLineId, l.sourceBookId, l.targetBookId,
               l.connectionTypeId
        FROM s.link l
        WHERE l.sourceLineId IN (SELECT id FROM daf_ids)
           OR l.targetLineId IN (SELECT id FROM daf_ids);
    """)
    n = db.execute('SELECT COUNT(*) FROM link').fetchone()[0]
    log(f'  {n:,} קישורים')

    log('line_ref — רק שורות שקישור מצביע עליהן')
    db.executescript("""
        CREATE TABLE line_ref AS
        SELECT l.id, l.bookId, l.lineIndex, l.heRef
        FROM s.line l
        WHERE l.id IN (SELECT sourceLineId FROM link
                       UNION SELECT targetLineId FROM link);
    """)
    n = db.execute('SELECT COUNT(*) FROM line_ref').fetchone()[0]
    log(f'  {n:,} שורות')

    # ‏line_dh הוא העוגן ברמת הקטע. הנרמול נצרב כאן ולא מחושב בזמן
    # ריצה: הלקוח מנרמל מחרוזת אחת, והמסד מחזיק 1.16 מיליון — חישוב
    # בזמן שאילתה היה סריקה מלאה במקום חיפוש.
    log('line_dh — דיבורי-המתחיל של הספרים שהגרף נוגע בהם')
    db.executescript("""
        -- ‏dhText עצמו אינו נשמר: הוא 90MB, ואיננו מציגים אותו —
        -- הלקוח מציג את הקטע שהוא כבר מחזיק. נשמרות רק שתי הצורות
        -- שמחפשים לפיהן.
        CREATE TABLE line_dh (
            bookId INTEGER, lineIndex INTEGER, dhNorm TEXT, dhTight TEXT);
    """)
    rows = db.execute("""
        SELECT d.bookId, d.lineIndex, d.dhText FROM s.line_dh d
        WHERE d.bookId IN (SELECT targetBookId FROM link
                           UNION SELECT sourceBookId FROM link)
    """).fetchall()

    def normalized():
        for book_id, idx, txt in rows:
            n = norm(txt or '')
            if n:
                yield (book_id, idx, n, tight(n))

    db.executemany('INSERT INTO line_dh VALUES (?,?,?,?)', normalized())
    n = db.execute('SELECT COUNT(*) FROM line_dh').fetchone()[0]
    log(f'  {n:,} דיבורי-מתחיל (מנורמלים; ריקים הושמטו)')

    log('אינדקסים')
    db.executescript("""
        CREATE INDEX ix_daf ON daf_line(masechet, daf);
        CREATE INDEX ix_link_src ON link(sourceLineId);
        CREATE INDEX ix_link_tgt ON link(targetLineId);
        CREATE UNIQUE INDEX ix_line_ref_id ON line_ref(id);
        CREATE INDEX ix_dh ON line_dh(bookId, lineIndex);
        CREATE INDEX ix_dh_norm ON line_dh(dhNorm);
        CREATE INDEX ix_dh_tight ON line_dh(dhTight);
        CREATE INDEX ix_book_id ON book(id);
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
    """)
    src_ver = db.execute(
        "SELECT value FROM s.schema_meta WHERE key='db_version'").fetchone()
    db.executemany('INSERT INTO meta VALUES (?,?)', [
        ('schema', '2'),
        ('otzaria_db_version', src_ver[0] if src_ver else '?'),
        ('built_at', time.strftime('%Y-%m-%dT%H:%M:%S')),
    ])
    db.commit()
    db.execute('DETACH s')
    log('VACUUM')
    db.execute('VACUUM')
    db.close()
    log(f'נכתב {out} — {os.path.getsize(out) / 1048576:.0f}MB')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--src', default=DEFAULT_SRC)
    p.add_argument('--out', default=DEFAULT_OUT)
    a = p.parse_args()
    build(a.src, a.out)

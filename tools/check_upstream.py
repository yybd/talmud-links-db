#!/usr/bin/env python3
"""האם אוצריא פרסמה מסד חדש? — הצד השני של מנגנון העדכון.

יש כאן שתי לולאות עדכון, ולא אחת:

  אוצריא → אנחנו   הסקריפט הזה. אוצריא מוציאה db_version חדש, ואז
                    צריך לבנות links.db חדש ולפרסם אותו.
  אנחנו → האפליקציה  המניפסט שב-publish.py, וההורדה ב-links_install.rs.

הסקריפט קורא את `library_stats.json` שבריליס של אוצריא — 80 בייט
שנושאים `db_version`, `books`, `links`, `lines` — ומשווה למה שנצרב
ל-`meta` שב-links.db שלנו. **אינו מוריד את 1.43GB.**

    python3 tools/check_upstream.py

יציאה 0 = מעודכן, 1 = יש חדש (נוח ל-CI), 2 = תקלה.
"""
import json, os, sqlite3, sys, urllib.request

LATEST = 'https://api.github.com/repos/Otzaria/SeforimLibrary/releases/latest'
STATS = 'library_stats.json'
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  'build', 'links.db')


def fetch_json(url):
    req = urllib.request.Request(url, headers={
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'talmud-ai-links-check',
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    try:
        rel = fetch_json(LATEST)
    except Exception as e:  # רשת, מגבלת קצב, שינוי במבנה — כולם "לא ידוע"
        print(f'לא ניתן לשאול את אוצריא: {e}', file=sys.stderr)
        return 2

    asset = next((a for a in rel.get('assets', []) if a['name'] == STATS), None)
    if not asset:
        print(f'הריליס {rel.get("tag_name")} אינו נושא {STATS} — '
              'ייתכן שהפורמט השתנה.', file=sys.stderr)
        return 2
    stats = fetch_json(asset['browser_download_url'])
    upstream = str(stats.get('db_version'))

    print(f'אוצריא: ריליס {rel.get("tag_name")}, db_version {upstream}')
    print(f'         {stats.get("books"):,} ספרים · {stats.get("lines"):,} שורות '
          f'· {stats.get("links"):,} קישורים')

    if not os.path.exists(DB):
        print('אין links.db מקומי — יש לבנות.')
        return 1
    con = sqlite3.connect(f'file:{DB}?immutable=1', uri=True)
    mine = dict(con.execute('SELECT key, value FROM meta')).get('otzaria_db_version')
    con.close()
    print(f'אצלנו:  db_version {mine} (נבנה ל-links.db)')

    if mine == upstream:
        print('\n✅ מעודכן — אין מה לבנות.')
        return 0
    print(f'\n🔔 יש מסד חדש באוצריא ({mine} → {upstream}). לבנות ולפרסם:\n'
          '   1. פתח את אוצריא ותן לה למשוך את הספרייה החדשה\n'
          '   2. python3 tools/build_links_db.py\n'
          f'   3. python3 tools/publish.py --tag v1-otzaria{upstream} --upload')
    return 1


if __name__ == '__main__':
    sys.exit(main())

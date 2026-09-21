#!/usr/bin/env python3
"""אריזת links.db לריליס, בדפוס של אוצריא.

אוצריא מפרסמת נכס גדול ולצדו **מניפסט קטן**, והלקוח מושך תמיד את
המניפסט קודם. המספרים שלה מוכיחים שזה עובד: המניפסט של הפאטץ' הורד
4,550 פעם מול 1,496 למסד המלא. אותו דפוס כאן — המניפסט הוא 300 בייט,
המסד הוא ~90MB, ואין סיבה להוריד את השני כדי לגלות שאין חדש.

    python3 tools/publish.py --tag v1-otzaria28 [--upload]

בלי --upload נכתבים רק הקבצים ל-dist/links/, לבדיקה. עם --upload הם
נדחפים לריליס ב-GitHub דרך gh.

**היעד הוא ריפו נפרד ופומבי**, ולא הריפו של הקוד. הסיבה מעשית: ריפו
פרטי מחזיר 404 על `releases/latest/download/…` לכל מי שאינו מאומת,
והאפליקציה אינה שולחת טוקן. זה בדיוק המבנה של אוצריא, שבה
SeforimLibrary נפרד מהאפליקציה — ובדרך גם שומר על הפרדה נכונה: הקוד
פרטי, הארטיפקט הנגזר פומבי.
"""
import argparse, hashlib, json, os, subprocess, sqlite3, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # שורש הריפו; tools/ הוא רמה אחת מתחתיו
DB = os.path.join(ROOT, 'build', 'links.db')
OUT = os.path.join(ROOT, 'build', 'dist')
MANIFEST = 'links-manifest.json'
ASSET = 'links.db.zst'
DATA_REPO = 'yybd/talmud-links-db'


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def meta(db_path):
    con = sqlite3.connect(f'file:{db_path}?immutable=1', uri=True)
    rows = dict(con.execute('SELECT key, value FROM meta'))
    con.close()
    return rows


def check_public(slug):
    """ריפו פרטי מחזיר 404 על נכסי ריליס לכל מי שאינו מאומת."""
    out = subprocess.run(['gh', 'api', f'repos/{slug}', '--jq', '.private'],
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f'אין גישה ל-{slug}: {out.stderr.strip()}')
    if out.stdout.strip() == 'true':
        sys.exit(f'{slug} פרטי — נכסי הריליס לא יהיו נגישים לאפליקציה.\n'
                 'ראה את ההערה בראש הקובץ.')


def main(tag, upload, base_url, slug):
    if not os.path.exists(DB):
        sys.exit(f'{DB} אינו קיים — הרץ tools/build_links_db.py')
    os.makedirs(OUT, exist_ok=True)
    asset = os.path.join(OUT, ASSET)

    print('דוחס ב-zstd -19 (כמו שאוצריא עושה)…', flush=True)
    t0 = time.time()
    subprocess.run(['zstd', '-19', '-T0', '-q', '-f', DB, '-o', asset], check=True)
    raw, comp = os.path.getsize(DB), os.path.getsize(asset)
    print(f'  {raw/1048576:.0f}MB → {comp/1048576:.0f}MB '
          f'({100*comp/raw:.0f}%) ב-{time.time()-t0:.0f}s')

    m = meta(DB)
    url = base_url or f'https://github.com/{slug}/releases/download/{tag}/{ASSET}'
    manifest = {
        'schema': int(m.get('schema', 1)),
        'otzariaDbVersion': m.get('otzaria_db_version'),
        'builtAt': m.get('built_at'),
        'tag': tag,
        'asset': ASSET,
        'url': url,
        'size': comp,
        'rawSize': raw,
        'sha256': sha256(asset),
    }
    path = os.path.join(OUT, MANIFEST)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps(manifest, ensure_ascii=False, indent=2))

    if not upload:
        print(f'\nנכתב ל-{OUT}. להעלאה בפועל: --upload')
        return

    check_public(slug)
    print(f'\nמעלה ל-{slug} תחת התג {tag}…', flush=True)
    exists = subprocess.run(['gh', 'release', 'view', tag, '-R', slug],
                            capture_output=True).returncode == 0
    if not exists:
        subprocess.run(['gh', 'release', 'create', tag, '-R', slug,
                        '--title', f'גרף הקישורים — {tag}',
                        '--notes', f'‏links.db schema {manifest["schema"]}, '
                                   f'נבנה ממסד אוצריא v{manifest["otzariaDbVersion"]}.'],
                       check=True)
    # ‏clobber: פרסום חוזר של אותו תג מחליף את הנכס במקום להיכשל.
    subprocess.run(['gh', 'release', 'upload', tag, asset, path,
                    '-R', slug, '--clobber'], check=True)
    print('הועלה.')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', required=True, help='תג הריליס, למשל v1-otzaria28')
    ap.add_argument('--upload', action='store_true')
    ap.add_argument('--base-url', help='לעקוף את כתובת ההורדה (אחסון אחר)')
    ap.add_argument('--repo', default=DATA_REPO, help=f'ריפו היעד (ברירת מחדל {DATA_REPO})')
    a = ap.parse_args()
    main(a.tag, a.upload, a.base_url, a.repo)

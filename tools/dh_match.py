#!/usr/bin/env python3
"""עיגון קטע בדף אל שורה במסד — הנרמול, והחילוץ מדפי shas-hadash.

זהו התאום בפייתון של `src/links/normalize.js`. **השניים חייבים להסכים
מילה במילה**: הנרמול נצרב לעמודה `dhNorm` בזמן הבנייה, והלקוח מנרמל
את הקטע שנבחר בזמן ריצה. אם הם נפרדים — החיפוש מפספס בשקט ואין שום
שגיאה שתסגיר את זה. `test_normalize_parity.py` מריץ את שניהם על אותה
דגימה ומשווה.

ארבעה דברים שהנרמול חייב לעשות, כל אחד מהם נמצא במדידה על הש"ס:
  1. ניקוד וטעמים — הדף מנוקד במקומות שהמסד אינו.
  2. פיסוק וגרשיים — ‏׳ ״ ' " . , : כולם מופיעים בצד אחד ולא בשני.
  3. זנב "וכו'" — הדף כותב 'מאימתי קורין וכו'.' והמסד 'מאימתי קורין'.
  4. רווחים — הדף מפריד ראשי-תיבות למילים נפרדות ('ס " ד' מול 'סד'),
     ולכן נשמרת גם גרסה בלי רווחים כלל.
"""
import gzip
import os
import re
import unicodedata
from collections import defaultdict

NIKUD = re.compile(r'[֑-ׇ]')
PUNCT = re.compile(r'[\'"׳״`.,:;()\[\]{}\-–—־!?*<>/\\|]')
TAGS = re.compile(r'<[^>]+>')
SPACE = re.compile(r'\s+')
TAIL = re.compile(r'\s*(וכו|וכולי|וגו|כו)\s*$')

WORD = re.compile(
    r'<span class="w[^"]*"[^>]*data-i="(\d+)"[^>]*data-seg="([^"]+)"([^>]*)>([^<]*)</span>')
LINE = re.compile(r'<div class="ln"[^>]*data-zone="([^"]+)"[^>]*>(.*?)</div>')


def norm(s: str) -> str:
    """הצורה המנורמלת. ריק פירושו 'אין על מה לעגן'."""
    s = unicodedata.normalize('NFC', s)
    s = TAGS.sub(' ', s)
    s = NIKUD.sub('', s)
    s = PUNCT.sub('', s)
    s = SPACE.sub(' ', s).strip()
    for _ in range(3):
        s = TAIL.sub('', s).strip()
    return s


def tight(s: str) -> str:
    """בלי רווחים — בשביל ראשי-תיבות שהדף מפריד והמסד מחבר."""
    return s.replace(' ', '')


def page_segments(path: str) -> dict:
    """{seg: (zone, dh, full)} — דיבור-המתחיל וכל טקסט הקטע, לפי סדר הקריאה."""
    h = gzip.open(path, 'rt', encoding='utf-8').read()
    zone_of, words, dh_words = {}, defaultdict(list), defaultdict(list)
    for zone, inner in LINE.findall(h):
        for i, seg, attrs, txt in WORD.findall(inner):
            zone_of.setdefault(seg, zone)
            words[seg].append((int(i), txt))
            if 'data-dh="1"' in attrs:
                dh_words[seg].append((int(i), txt))
    out = {}
    for seg, ws in words.items():
        ws.sort()
        dw = sorted(dh_words.get(seg, []))
        out[seg] = (zone_of.get(seg, '?'),
                    ' '.join(w for _, w in dw),
                    ' '.join(w for _, w in ws))
    return out


def daf_dir(repo_root: str) -> str:
    return os.path.join(repo_root, 'public', 'shas-hadash', 'daf')

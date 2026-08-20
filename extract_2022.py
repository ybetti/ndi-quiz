# -*- coding: utf-8 -*-
"""
2022年度NDIレベル2問題（春期・秋期／ET・PT・RT・UT）のPDFからCSVを生成する。

使い方:
    python extract_2022.py            # CSVと図を出力
    python extract_2022.py --dry-run  # 集計のみ（ファイルは書き出さない）

出力:
    questions/{et,pt,rt,ut}_2022_{04,10}.csv
    questions/images/{et,pt,rt,ut}_2022_{04,10}_q{N}.png  （図のある問題のみ）
"""

import csv
import os
import re
import sys

import fitz

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, 'questions')
IMG_DIR = os.path.join(OUT_DIR, 'images')

# 対象PDF: (出力プレフィックス, PDFパス, 問番号の書式, 解答部の書式)
#   qstyle: 'mon' = 「問N」 / 'num' = 「N.」
#   astyle: 'table' = 解答表 / 'lines' = 「問N/解答：X/解説：…」の行形式
TARGETS = [
    ('et_2022_04', r'問題\2022春NDIレベル2問題\2022S-ET2-QA.pdf', 'mon', 'lines'),
    ('pt_2022_04', r'問題\2022春NDIレベル2問題\2022S-PT2-QA.pdf', 'mon', 'table'),
    ('rt_2022_04', r'問題\2022春NDIレベル2問題\2022S-RT2-QA.pdf', 'num', 'table'),
    ('ut_2022_04', r'問題\2022春NDIレベル2問題\2022S-UT2-QA.pdf', 'mon', 'table'),
    ('et_2022_10', r'問題\2022秋NDIレベル2問題\2022A-ET2-QA.pdf', 'mon', 'lines'),
    ('pt_2022_10', r'問題\2022秋NDIレベル2問題\2022A-PT2-QA.pdf', 'mon', 'table'),
    ('rt_2022_10', r'問題\2022秋NDIレベル2問題\2022A-RT2-QA.pdf', 'num', 'table'),
    ('ut_2022_10', r'問題\2022秋NDIレベル2問題\2022A-UT2-QA.pdf', 'mon', 'table'),
]

LETTERS = 'abcdef'
# 全角英小文字→半角
ZEN2HAN = {chr(0xFF41 + i): chr(ord('a') + i) for i in range(26)}


def to_han_letter(ch):
    return ZEN2HAN.get(ch, ch).lower()


def norm_space(text):
    """CSVの1行に収めるため、改行と連続空白を1つの空白にまとめる"""
    text = text.replace('　', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def strip_running_heads(page_texts):
    """全ページに繰り返し現れるヘッダ・フッタ行とページ番号行を取り除く"""
    def key(line):
        return re.sub(r'[\d０-９\s]', '', line)

    def edge_indexes(lines):
        """ページ上端・下端の非空行のインデックス（各3行まで）"""
        nonempty = [i for i, l in enumerate(lines) if l.strip()]
        return set(nonempty[:3]) | set(nonempty[-3:])

    counts = {}
    for t in page_texts:
        lines = t.split('\n')
        seen = set()
        for i in edge_indexes(lines):
            s = lines[i].strip()
            if not s or len(s) > 40:
                continue
            k = key(s)
            if k and k not in seen:
                seen.add(k)
                counts[k] = counts.get(k, 0) + 1

    threshold = max(3, int(len(page_texts) * 0.4))
    running = {k for k, c in counts.items() if c >= threshold}

    cleaned = []
    for t in page_texts:
        lines = t.split('\n')
        edges = edge_indexes(lines)
        out = []
        for i, line in enumerate(lines):
            s = line.strip()
            if i in edges and s and len(s) <= 40:
                if key(s) in running or re.fullmatch(r'[-‐－\s]*[\d０-９]+[-‐－\s]*', s):
                    out.append('')
                    continue
            out.append(line)
        cleaned.append('\n'.join(out))
    return cleaned


# 選択肢の末尾が次の見出しや資料へ流れ込むのを断ち切るための区切り
BREAK_RE = re.compile(
    r'\n[ \t]*\n[ \t]*\n'          # 空行が2行以上続く＝段落の切れ目
    r'|\n[ \t]*[＜<]\s*資料'
    r'|\n[ \t]*附属書'
    r'|\n[ \t]*図[ 　]*[０-９0-9]'
    r'|\n[ \t]*解[ 　]*答[ 　]*例'
)


def cut_at_break(text):
    m = BREAK_RE.search(text)
    return text[:m.start()] if m else text


# --------------------------------------------------------------------------
# 解答部の開始ページを検出する
# --------------------------------------------------------------------------

def find_answer_start(doc, astyle):
    if astyle == 'lines':
        for i in range(len(doc)):
            if '解答：' in doc[i].get_text():
                return i
    else:
        for i in range(len(doc)):
            page = doc[i]
            try:
                tabs = page.find_tables()
            except Exception:
                continue
            for t in tabs.tables:
                for row in t.extract():
                    if len(row) >= 3 and (row[0] or '').strip() == '1':
                        cell = (row[1] or '').strip()
                        if len(cell) == 1 and to_han_letter(cell) in LETTERS:
                            return i
    return None


# --------------------------------------------------------------------------
# 問題部の解析
# --------------------------------------------------------------------------

def question_marker(n, qstyle):
    if qstyle == 'mon':
        return re.compile(r'^[ 　]*問[ 　]*%d(?![0-9])' % n, re.M)
    return re.compile(r'^[ 　]*%d[ 　]*[.．](?=[ 　]*\S)' % n, re.M)


def split_questions(text, qstyle, max_gap=3):
    """問1から順に番号を探し、(番号, 開始位置) のリストを返す"""
    spans = []
    pos = 0
    n = 1
    while True:
        found = None
        for cand in range(n, n + max_gap + 1):
            m = question_marker(cand, qstyle).search(text, pos)
            if m:
                # 大きく飛ぶ場合は近い方を優先するため最初に見つかったものを採用
                found = (cand, m)
                break
        if not found:
            break
        cand, m = found
        spans.append((cand, m.start(), m.end()))
        pos = m.end()
        n = cand + 1
    return spans


CHOICE_RE = re.compile(r'(?<![0-9A-Za-zａ-ｚ])[（(]?([a-fａ-ｆ])[)）]')

# 問題文末尾に付く参照表記を落とすためのパターン
REF_TAIL_RE = re.compile(
    r'[（(][^（()）]*(?:問|Ⅰ|Ⅱ|Ⅲ|類|NDT)[^（()）]*[）)]\s*'
    r'|〔[^〔〕]*(?:Ⅰ|Ⅱ|Ⅲ|問)[^〔〕]*〕\s*'
)


def parse_choices(block):
    """本文ブロックから選択肢を抜き出す。戻り値: (問題文, {ラベル: 文字列})"""
    matches = list(CHOICE_RE.finditer(block))
    picked = []
    expect = 0
    for m in matches:
        if to_han_letter(m.group(1)) == LETTERS[expect]:
            picked.append(m)
            expect += 1
            if expect >= len(LETTERS):
                break
    if len(picked) < 4:
        return None, None

    choices = {}
    for i, m in enumerate(picked):
        end = picked[i + 1].start() if i + 1 < len(picked) else len(block)
        choices[LETTERS[i]] = norm_space(cut_at_break(block[m.end():end]))

    qtext = block[:picked[0].start()]
    return qtext, choices


def is_multi_blank(choices):
    """［１］［２］…と解答群が複数ある問題は1問1答の形式に収まらないため除外する"""
    for text in choices.values():
        if CHOICE_RE.search(text):
            return True
    return False


def clean_question_text(qtext, qstyle):
    qtext = re.sub(r'^[ 　]*(?:問[ 　]*\d+|\d+[ 　]*[.．])', '', qtext, count=1)
    qtext = norm_space(qtext)
    qtext = qtext.replace('〔解答群〕', ' ')
    qtext = re.sub(r'〔[０-９0-9]+〕', ' ', qtext)
    # 出典表記（問1.1.16）〔Ⅰ1.1.1〕などを除去
    qtext = REF_TAIL_RE.sub(' ', qtext)
    return norm_space(qtext)


def parse_question_section(doc, first_page, last_page, qstyle):
    """問題部を解析して {番号: {question, choices, page, y0, y1}} を返す"""
    page_texts = strip_running_heads([doc[p].get_text()
                                      for p in range(first_page, last_page + 1)])
    offsets = []
    total = 0
    for t in page_texts:
        offsets.append(total)
        total += len(t) + 1
    text = '\n'.join(page_texts)

    spans = split_questions(text, qstyle)
    all_nums = [s[0] for s in spans]
    result = {}
    skipped = []
    for i, (num, start, _end) in enumerate(spans):
        end = spans[i + 1][1] if i + 1 < len(spans) else len(text)
        block = text[start:end]
        qtext, choices = parse_choices(block)
        if choices is None:
            skipped.append((num, 'no_choices'))
            continue
        if len(choices) > 5:
            skipped.append((num, 'too_many_choices'))
            continue
        if is_multi_blank(choices):
            skipped.append((num, 'multi_blank'))
            continue
        qtext = clean_question_text(qtext, qstyle)
        if len(qtext) < 6:
            skipped.append((num, 'short_text'))
            continue
        # 問題が始まるページを求める
        pidx = 0
        for k, off in enumerate(offsets):
            if start >= off:
                pidx = k
            else:
                break
        result[num] = {
            'question': qtext,
            'choices': choices,
            'page': first_page + pidx,
        }
    return result, skipped, all_nums


# --------------------------------------------------------------------------
# 解答部の解析
# --------------------------------------------------------------------------

def parse_answers_table(doc, first_page, last_page):
    answers = {}
    for p in range(first_page, last_page + 1):
        page = doc[p]
        try:
            tabs = page.find_tables()
        except Exception:
            continue
        if not tabs.tables:
            continue
        # 最も面積の大きい表を解答表とみなす（入れ子の表を除外するため）
        main = max(tabs.tables, key=lambda t: (t.bbox[2] - t.bbox[0]) * (t.bbox[3] - t.bbox[1]))
        for row in main.extract():
            if len(row) < 3:
                continue
            num_cell = norm_space(row[0] or '')
            m = re.match(r'^(\d+)$', num_cell)
            if not m:
                continue
            num = int(m.group(1))
            ans_cell = norm_space(row[1] or '')
            am = re.search(r'[a-fａ-ｆ]', ans_cell)
            if not am:
                continue
            expl = norm_space(row[2] or '')
            if num not in answers:
                answers[num] = {'answer': to_han_letter(am.group(0)), 'explanation': expl}
    return answers


ANS_LINE_RE = re.compile(r'^[ 　]*解答[:：]\s*(.+)$', re.M)


def parse_answers_lines(doc, first_page, last_page):
    """ET形式: 「問N」「解答：ｃ」「解説：…」「過問：…」"""
    text = '\n'.join(strip_running_heads([doc[p].get_text()
                                          for p in range(first_page, last_page + 1)]))
    spans = split_questions(text, 'mon')
    answers = {}
    for i, (num, start, _end) in enumerate(spans):
        end = spans[i + 1][1] if i + 1 < len(spans) else len(text)
        block = text[start:end]
        am = ANS_LINE_RE.search(block)
        if not am:
            continue
        letter_m = re.search(r'[a-fａ-ｆ]', am.group(1))
        if not letter_m:
            continue
        rest = block[am.end():]
        # 解説：以降、過問：の手前までを解説とする
        expl = rest
        em = re.search(r'^[ 　]*解説[:：]', rest, re.M)
        if em:
            expl = rest[em.end():]
        km = re.search(r'^[ 　]*(?:過問|参考)[:：]', expl, re.M)
        if km:
            expl = expl[:km.start()]
        note = norm_space(am.group(1))
        note = re.sub(r'^[a-fａ-ｆ]\s*', '', note)
        expl = norm_space(expl)
        if note:
            expl = norm_space(note + ' ' + expl)
        answers[num] = {'answer': to_han_letter(letter_m.group(0)), 'explanation': expl}
    return answers


# --------------------------------------------------------------------------
# 図の抽出
# --------------------------------------------------------------------------

def question_regions(doc, all_nums, first_page, last_page, qstyle):
    """各問題の開始y座標をページ上の行から求める（除外した問題も含めて全番号）"""
    wanted = set(all_nums)
    starts = {}
    for p in range(first_page, last_page + 1):
        for block in doc[p].get_text('dict')['blocks']:
            if block.get('type') != 0:
                continue
            for line in block['lines']:
                head = ''.join(s['text'] for s in line['spans']).lstrip()
                if qstyle == 'mon':
                    m = re.match(r'問[ 　]*(\d+)(?![0-9])', head)
                else:
                    m = re.match(r'(\d+)[ 　]*[.．]\s*\S', head)
                if not m:
                    continue
                num = int(m.group(1))
                if num in wanted and num not in starts:
                    starts[num] = (p, line['bbox'][1])
    return starts


# 問題本体の終わりを示す見出し（巻末資料など）。図の切り出し範囲をここで止める
SECTION_HEAD_RE = re.compile(r'^[ 　]*(?:[＜<]\s*資料|資料[０-９0-9]|附属書|付属書|解[ 　]*答[ 　]*例)')


def section_head_y(page, y0):
    """y0より下で巻末資料などの見出しが始まるy座標。無ければNone"""
    best = None
    for block in page.get_text('dict')['blocks']:
        if block.get('type') != 0:
            continue
        for line in block['lines']:
            text = ''.join(s['text'] for s in line['spans'])
            if line['bbox'][1] > y0 and SECTION_HEAD_RE.match(text):
                if best is None or line['bbox'][1] < best:
                    best = line['bbox'][1]
    return best


def question_rects(doc, starts, ordered, idx, last_page, max_pages=2):
    """問題の占める領域を (ページ, y0, y1) のリストで返す。ページをまたぐ場合は複数返す"""
    num = ordered[idx]
    p0, y0 = starts[num]
    nxt = None
    for m in ordered[idx + 1:]:
        if m in starts:
            nxt = starts[m]
            break
    if nxt and nxt[0] == p0:
        cut = section_head_y(doc[p0], y0)
        return [(p0, y0, min(nxt[1], cut) if cut else nxt[1])]

    end_page = min(nxt[0] if nxt else last_page, p0 + max_pages - 1, last_page)
    end_y = nxt[1] if (nxt and nxt[0] == end_page) else doc[end_page].rect.y1 - 40
    rects = []
    for p in range(p0, end_page + 1):
        top = y0 if p == p0 else 40.0
        bottom = end_y if p == end_page else doc[p].rect.y1 - 40
        cut = section_head_y(doc[p], top)
        if cut:
            bottom = min(bottom, cut)
        if bottom - top > 10:
            rects.append((p, top, bottom))
        if cut:
            break
    return rects


def content_bottom(page, y0, y1):
    """領域内で実際に中身がある最下端のy座標"""
    bottom = y0
    for b in page.get_text('dict')['blocks']:
        bx0, by0, bx1, by1 = b['bbox']
        if by0 < y1 and by1 > y0:
            if b.get('type') == 1 or any(
                    ''.join(s['text'] for s in ln['spans']).strip()
                    for ln in b.get('lines', [])):
                bottom = max(bottom, min(by1, y1))
    for dr in page.get_drawings():
        r = dr['rect']
        if r.y0 < y1 and r.y1 > y0 and r.width * r.height > 100:
            bottom = max(bottom, min(r.y1, y1))
    return bottom


def has_figure(page, y0, y1):
    """指定したy範囲に図（画像またはベクター描画）があるか"""
    for b in page.get_text('dict')['blocks']:
        if b.get('type') == 1:
            bx0, by0, bx1, by1 = b['bbox']
            if by1 > y0 and by0 < y1 and (by1 - by0) > 25:
                return True
    try:
        drawings = page.get_drawings()
    except Exception:
        drawings = []
    area = 0.0
    for dr in drawings:
        r = dr['rect']
        if r.y1 > y0 and r.y0 < y1:
            area += max(0.0, r.width) * max(0.0, r.height)
    return area > 4000


def render_regions(doc, rects, out_path, zoom=2.5):
    """領域を上から順に縦につなげて1枚のPNGにする"""
    pixmaps = []
    for p, y0, y1 in rects:
        page = doc[p]
        bottom = min(y1, content_bottom(page, y0, y1) + 6)
        clip = fitz.Rect(page.rect.x0 + 25, max(page.rect.y0, y0 - 4),
                         page.rect.x1 - 25, bottom)
        if clip.height < 20:
            continue
        pixmaps.append(page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip))
    if not pixmaps:
        return False
    if len(pixmaps) == 1:
        pixmaps[0].save(out_path)
        return True

    width = max(p.width for p in pixmaps)
    height = sum(p.height for p in pixmaps)
    out = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height), False)
    out.clear_with(255)
    y = 0
    for p in pixmaps:
        p.set_origin(0, y)
        out.copy(p, p.irect)
        y += p.height
    out.save(out_path)
    return True


# --------------------------------------------------------------------------

def process(prefix, pdf_rel, qstyle, astyle, dry_run):
    path = os.path.join(BASE_DIR, pdf_rel)
    doc = fitz.open(path)
    ans_start = find_answer_start(doc, astyle)
    if ans_start is None:
        print(f'  [!] {prefix}: 解答部が見つかりません')
        doc.close()
        return None

    questions, skipped, all_nums = parse_question_section(doc, 0, ans_start - 1, qstyle)
    if astyle == 'table':
        answers = parse_answers_table(doc, ans_start, len(doc) - 1)
    else:
        answers = parse_answers_lines(doc, ans_start, len(doc) - 1)

    starts = question_regions(doc, all_nums, 0, ans_start - 1, qstyle)
    ordered_all = sorted(starts)

    rows = []
    no_answer = []
    figures = 0
    ordered = sorted(questions)
    for idx, num in enumerate(ordered):
        q = questions[num]
        a = answers.get(num)
        if not a:
            no_answer.append(num)
            continue
        if a['answer'] not in q['choices']:
            no_answer.append(num)
            continue

        image = ''
        if num in starts:
            rects = question_rects(doc, starts, ordered_all,
                                   ordered_all.index(num), ans_start - 1)
            if any(has_figure(doc[p], y0, y1) for p, y0, y1 in rects):
                fname = f'{prefix}_q{num}.png'
                if dry_run:
                    image = fname
                    figures += 1
                elif render_regions(doc, rects, os.path.join(IMG_DIR, fname)):
                    image = fname
                    figures += 1

        ch = dict(q['choices'])
        if any(not v for v in ch.values()):
            # 選択肢が図で示されている問題。図があれば図中の記号を指す文言を入れる
            if not image:
                no_answer.append(num)
                continue
            for k in ch:
                if not ch[k]:
                    ch[k] = f'図の（{k}）'
        rows.append({
            'id': num,
            'question': q['question'],
            'choices': ch,
            'answer': a['answer'],
            'explanation': a['explanation'],
            'image': image,
        })

    five = any(len(r['choices']) == 5 for r in rows)
    out_path = os.path.join(OUT_DIR, prefix + '.csv')
    if not dry_run:
        with open(out_path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            if five:
                w.writerow(['id', 'question', 'choice_a', 'choice_b', 'choice_c',
                            'choice_d', 'choice_e', 'answer', 'explanation', 'image'])
            else:
                w.writerow(['id', 'question', 'choice_a', 'choice_b', 'choice_c',
                            'choice_d', 'answer', 'explanation', 'image'])
            for r in rows:
                ch = r['choices']
                cols = [r['id'], r['question'], ch.get('a', ''), ch.get('b', ''),
                        ch.get('c', ''), ch.get('d', '')]
                if five:
                    cols.append(ch.get('e', ''))
                cols += [r['answer'], r['explanation'], r['image']]
                w.writerow(cols)

    print(f'  {prefix}: 解答部p{ans_start} / 問題{len(questions)}件 解答{len(answers)}件 '
          f'→ 出力{len(rows)}問（{"5択あり" if five else "4択"}）図{figures}件')
    if skipped:
        by_reason = {}
        for num, reason in skipped:
            by_reason.setdefault(reason, []).append(num)
        for reason, nums in sorted(by_reason.items()):
            print(f'      除外({reason}): {len(nums)}件 {nums[:20]}')
    if no_answer:
        print(f'      解答が対応せず除外: {len(no_answer)}件 {no_answer[:20]}')
    doc.close()
    return len(rows)


def main():
    dry_run = '--dry-run' in sys.argv
    os.makedirs(IMG_DIR, exist_ok=True)
    print('2022年度 NDIレベル2 問題を抽出します' + ('（dry-run）' if dry_run else ''))
    total = 0
    for prefix, pdf_rel, qstyle, astyle in TARGETS:
        n = process(prefix, pdf_rel, qstyle, astyle, dry_run)
        total += n or 0
    print(f'合計 {total} 問')


if __name__ == '__main__':
    main()

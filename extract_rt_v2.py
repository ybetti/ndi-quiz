# -*- coding: utf-8 -*-
"""
RT問題PDFから問21以降をCSVに追加するスクリプト
"""

import fitz
import re
import csv
import os

def extract_questions_and_answers():
    pdf_path = r'問題\2024A-RT2-QA.pdf'
    output_path = r'questions\rt_2024_10.csv'

    doc = fitz.open(pdf_path)

    # 問題部分のテキスト（ページ3-25あたり）
    questions_text = ''
    for page_num in range(2, 25):
        page = doc[page_num]
        questions_text += page.get_text() + '\n'

    # 解答部分のテキスト（ページ26以降）
    answers_text = ''
    for page_num in range(25, len(doc)):
        page = doc[page_num]
        answers_text += page.get_text() + '\n'

    doc.close()

    # 問題を抽出（問21から）
    questions = {}

    # 問題パターン: "番号. 問題文" と選択肢 "a) ... b) ... c) ... d) ..."
    lines = questions_text.split('\n')
    current_q_num = None
    current_text = []

    for line in lines:
        # 問題番号の検出
        match = re.match(r'^(\d+)[.．]\s*(.*)$', line.strip())
        if match:
            # 前の問題を保存
            if current_q_num and current_q_num >= 21:
                full_text = ' '.join(current_text)
                questions[current_q_num] = full_text

            current_q_num = int(match.group(1))
            current_text = [match.group(2)] if match.group(2) else []
        elif current_q_num:
            current_text.append(line.strip())

    # 最後の問題を保存
    if current_q_num and current_q_num >= 21:
        full_text = ' '.join(current_text)
        questions[current_q_num] = full_text

    # 解答を抽出
    answers = {}

    # 解答パターン: "番号 改行 a/b/c/d 改行 解説..."
    answer_pattern = re.compile(r'^(\d+)\s*$')
    answer_lines = answers_text.split('\n')

    i = 0
    while i < len(answer_lines):
        line = answer_lines[i].strip()
        match = answer_pattern.match(line)
        if match:
            q_num = int(match.group(1))
            # 次の行が解答
            if i + 1 < len(answer_lines):
                answer_line = answer_lines[i + 1].strip().lower()
                if answer_line in ['a', 'b', 'c', 'd']:
                    # 解説を収集
                    explanation_lines = []
                    j = i + 2
                    while j < len(answer_lines):
                        next_line = answer_lines[j].strip()
                        # 次の問題番号が来たら終了
                        if answer_pattern.match(next_line):
                            break
                        explanation_lines.append(next_line)
                        j += 1

                    explanation = ' '.join(explanation_lines)[:400]
                    answers[q_num] = {'answer': answer_line, 'explanation': explanation}
                    i = j - 1
        i += 1

    # 問題から選択肢を抽出
    parsed_questions = {}
    for q_num, text in questions.items():
        # 選択肢を抽出
        choice_pattern = re.compile(r'([a-d])\)\s*(.+?)(?=\s*[a-d]\)|\s*$)', re.DOTALL)
        choices_matches = list(choice_pattern.finditer(text))

        if choices_matches:
            # 問題文は最初の選択肢の前まで
            question_text = text[:choices_matches[0].start()].strip()
            choices = {}
            for m in choices_matches:
                label = m.group(1)
                choice_text = m.group(2).strip().replace('\n', ' ')
                choices[label] = choice_text

            if len(choices) == 4:
                parsed_questions[q_num] = {
                    'question': question_text.replace('\n', ' '),
                    'choices': choices
                }

    # 既存のCSVを読み込み
    existing_questions = []
    with open(output_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing_questions.append(row)

    print(f'既存の問題数: {len(existing_questions)}')
    print(f'抽出した問題数 (問21以降): {len(parsed_questions)}')
    print(f'抽出した解答数: {len(answers)}')

    # CSVに書き出し（既存の問題 + 新しい問題）
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'question', 'choice_a', 'choice_b', 'choice_c', 'choice_d', 'answer', 'explanation'])

        # 既存の問題を書き出し
        for row in existing_questions:
            writer.writerow([
                row['id'],
                row['question'],
                row['choice_a'],
                row['choice_b'],
                row['choice_c'],
                row['choice_d'],
                row['answer'],
                row['explanation']
            ])

        # 新しい問題を追加
        added = 0
        for q_num in sorted(parsed_questions.keys()):
            if q_num in answers:
                q = parsed_questions[q_num]
                a = answers[q_num]
                writer.writerow([
                    q_num,
                    q['question'],
                    q['choices'].get('a', ''),
                    q['choices'].get('b', ''),
                    q['choices'].get('c', ''),
                    q['choices'].get('d', ''),
                    a['answer'],
                    a['explanation']
                ])
                added += 1

    print(f'追加した問題数: {added}')
    print(f'合計問題数: {len(existing_questions) + added}')

if __name__ == "__main__":
    extract_questions_and_answers()

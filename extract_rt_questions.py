# -*- coding: utf-8 -*-
"""
RT問題PDFからCSVを生成するスクリプト
"""

import fitz
import re
import csv
import os

def extract_rt_questions():
    pdf_path = r'問題\2024A-RT2-QA.pdf'
    output_path = r'questions\rt_2024_10.csv'

    if not os.path.exists(pdf_path):
        print(f"PDFファイルが見つかりません: {pdf_path}")
        return

    doc = fitz.open(pdf_path)

    # 全テキストを抽出
    all_text = ''
    for page_num in range(2, len(doc)):
        page = doc[page_num]
        all_text += page.get_text() + '\n'

    doc.close()

    # 問題と解答を抽出
    questions = {}
    answers = {}

    # 問題パターン: "番号. 問題文"
    question_pattern = re.compile(r'^(\d+)\.\s+(.+?)(?=^\d+\.\s|\Z)', re.MULTILINE | re.DOTALL)

    # 解答パターン: "番号\n回答\n解説"
    answer_pattern = re.compile(r'^(\d+)\s*\n([a-d])\s*\n(.+?)(?=^\d+\s*\n[a-d]\s*\n|\Z)', re.MULTILINE | re.DOTALL)

    # 問題を抽出
    for match in question_pattern.finditer(all_text):
        q_num = int(match.group(1))
        q_text = match.group(2).strip()

        # 選択肢を抽出
        choices = {}
        choice_pattern = re.compile(r'([a-d])\)\s*(.+?)(?=[a-d]\)|\Z)', re.DOTALL)
        choice_matches = list(choice_pattern.finditer(q_text))

        if choice_matches:
            # 問題文は最初の選択肢の前まで
            question_text = q_text[:choice_matches[0].start()].strip()
            for cm in choice_matches:
                choice_label = cm.group(1)
                choice_text = cm.group(2).strip().replace('\n', ' ')
                choices[choice_label] = choice_text

            if len(choices) >= 4:
                questions[q_num] = {
                    'question': question_text.replace('\n', ' '),
                    'choices': choices
                }

    # 解答を抽出
    for match in answer_pattern.finditer(all_text):
        a_num = int(match.group(1))
        answer = match.group(2).lower()
        explanation = match.group(3).strip().replace('\n', ' ')
        answers[a_num] = {
            'answer': answer,
            'explanation': explanation[:500]  # 解説は500文字まで
        }

    # CSVに書き出し
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'question', 'choice_a', 'choice_b', 'choice_c', 'choice_d', 'answer', 'explanation'])

        for q_num in sorted(questions.keys()):
            if q_num in answers:
                q = questions[q_num]
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

    print(f"抽出完了: {len(questions)}問中、解答付き{len([q for q in questions if q in answers])}問をCSVに保存しました。")
    print(f"出力ファイル: {output_path}")

if __name__ == "__main__":
    extract_rt_questions()

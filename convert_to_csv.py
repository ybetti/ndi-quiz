import re
import csv
import os

# index.htmlを読み込み
with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 問題データを抽出する正規表現
pattern = r'\{\s*id:\s*(\d+),\s*question:\s*"([^"]*)",\s*choices:\s*\{\s*a:\s*"([^"]*)",\s*b:\s*"([^"]*)",\s*c:\s*"([^"]*)",\s*d:\s*"([^"]*)"\s*\},\s*answer:\s*"([^"]*)",\s*explanation:\s*"([^"]*)"\s*\}'

# UTとMTの問題を抽出
ut_match = re.search(r'const utQuestions = \[(.*?)\];', content, re.DOTALL)
mt_match = re.search(r'const mtQuestions = \[(.*?)\];', content, re.DOTALL)

def extract_and_save(data_str, filename):
    matches = re.findall(pattern, data_str)

    # questionsフォルダを作成
    os.makedirs('questions', exist_ok=True)

    with open(f'questions/{filename}', 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        # ヘッダー
        writer.writerow(['id', 'question', 'choice_a', 'choice_b', 'choice_c', 'choice_d', 'answer', 'explanation'])

        for match in matches:
            writer.writerow(match)

    print(f'{filename}: {len(matches)}問を出力しました')

if ut_match:
    extract_and_save(ut_match.group(1), 'ut_questions.csv')

if mt_match:
    extract_and_save(mt_match.group(1), 'mt_questions.csv')

print('変換完了！questionsフォルダにCSVファイルが作成されました。')

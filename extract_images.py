# -*- coding: utf-8 -*-
"""
PDFから問題の図を抽出するスクリプト
使い方: python extract_images.py
"""

import fitz
import os
import re
import sys

# 出力ディレクトリ
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'questions', 'images')

# 処理するPDFファイル
PDF_FILES = {
    'xr_2024_04': '問題/2024.4 X線問題.pdf',
    'xr_2024_10': '問題/2024.10 X線問題.pdf',
    'xr_2025_04': '問題/2025.4 X線問題.pdf',
    'xr_2025_10': '問題/2025.10 X線問題.pdf',
    'ut_2023': '問題/2023S-UT2-QA.pdf',
    'mt_2024': '問題/2024A-MT2-QA.pdf',
    'pt_2024': '問題/2024A-PT2-QA.pdf',
    'rt_2024': '問題/2024A-RT2-QA.pdf',
}

def extract_figure_from_page(page, page_rect, zoom=2):
    """ページから図の部分を抽出する"""
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, clip=page_rect)
    return pix

def find_figure_region(page):
    """ページ内の図の領域を検出する（テキストブロックの間の空白領域）"""
    # テキストブロックを取得
    blocks = page.get_text("dict")["blocks"]

    page_rect = page.rect
    figure_regions = []

    # 図を含む可能性のある領域を探す
    # テキストブロックの間にある大きな空白領域を図とみなす
    text_blocks = [b for b in blocks if b.get("type") == 0]  # テキストブロックのみ

    if not text_blocks:
        return None

    # Y座標でソート
    text_blocks.sort(key=lambda b: b["bbox"][1])

    # 連続するテキストブロック間の隙間を調べる
    for i in range(len(text_blocks) - 1):
        current_bottom = text_blocks[i]["bbox"][3]
        next_top = text_blocks[i + 1]["bbox"][1]
        gap = next_top - current_bottom

        # 大きな隙間（50ピクセル以上）があれば図の可能性
        if gap > 50:
            # 図の領域を定義（少し余白を持たせる）
            figure_rect = fitz.Rect(
                page_rect.x0 + 20,  # 左余白
                current_bottom + 5,
                page_rect.x1 - 20,  # 右余白
                next_top - 5
            )
            figure_regions.append(figure_rect)

    return figure_regions

def extract_images_from_pdf(pdf_key, pdf_path):
    """PDFから図を抽出する"""
    full_path = os.path.join(os.path.dirname(__file__), pdf_path)

    if not os.path.exists(full_path):
        print(f"  ファイルが見つかりません: {pdf_path}")
        return []

    doc = fitz.open(full_path)
    extracted = []

    print(f"  ページ数: {len(doc)}")

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()

        # 図を含むページかチェック
        if '図' not in text and 'グラフ' not in text:
            continue

        # 問題番号を抽出
        question_match = re.search(r'問\s*(\d+)', text)
        if not question_match:
            continue

        question_num = question_match.group(1)

        # ページ全体を画像として保存（図の領域検出は複雑なため）
        zoom = 2.5  # 高解像度
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        filename = f"{pdf_key}_q{question_num}.png"
        output_path = os.path.join(OUTPUT_DIR, filename)
        pix.save(output_path)

        print(f"    問{question_num} → {filename}")
        extracted.append({
            'question': question_num,
            'filename': filename,
            'page': page_num + 1
        })

    doc.close()
    return extracted

def main():
    print("=" * 50)
    print("PDFから問題の図を抽出します")
    print("=" * 50)

    # 出力ディレクトリを作成
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"\n出力先: {OUTPUT_DIR}\n")

    all_extracted = {}

    for pdf_key, pdf_path in PDF_FILES.items():
        print(f"\n処理中: {pdf_path}")
        extracted = extract_images_from_pdf(pdf_key, pdf_path)
        if extracted:
            all_extracted[pdf_key] = extracted

    # 結果のサマリー
    print("\n" + "=" * 50)
    print("抽出完了")
    print("=" * 50)

    total = sum(len(v) for v in all_extracted.values())
    print(f"\n合計 {total} 個の図を抽出しました。\n")

    # CSVへの追加方法を表示
    print("【CSVへの追加方法】")
    print("CSVファイルの最後の列に画像ファイル名を追加してください。")
    print("\n例（4択問題）:")
    print("id,question,choice_a,choice_b,choice_c,choice_d,answer,explanation,image")
    print('7,"下図のように...",9m,12m,17m,22m,d,"説明...",xr_2024_04_q7.png')
    print("\n例（5択問題）:")
    print("id,question,choice_a,choice_b,choice_c,choice_d,choice_e,answer,explanation,image")
    print('7,"下図のように...",9m,12m,17m,22m,27m,d,"説明...",xr_2024_04_q7.png')

if __name__ == "__main__":
    main()

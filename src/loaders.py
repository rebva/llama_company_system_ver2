"""
ドキュメントローダー
- 各種ファイル形式を読み込み、langchain.schema.Document オブジェクトを返す
- metadata に source（ファイル名）を設定
"""
import os  # ファイルやディレクトリ操作用
from typing import List  # 型ヒント用
import fitz  # PyMuPDF: PDF操作ライブラリ
import pandas as pd  # データ解析ライブラリ
from langchain.schema import Document  # LangChain のドキュメントオブジェクトクラス
from src.config import DATA_FOLDER  # ドキュメント格納フォルダパス設定

def load_pdfs() -> List[Document]:
    """
    DATA_FOLDER 配下の .pdf ファイルをすべて読み込み、
    ページごとにテキスト抽出して Document リストを返す
    """
    docs: List[Document] = []  # ドキュメント格納用リスト
    for fn in os.listdir(DATA_FOLDER):  # フォルダ内のファイルをループ
        if fn.lower().endswith(".pdf"):  # PDFファイルのみ対象
            path = os.path.join(DATA_FOLDER, fn)  # フルパスを作成
            pdf = fitz.open(path)  # PDFファイルを開く
            # 各ページのテキストを改行で結合
            text = "\n".join(page.get_text() for page in pdf)
            # Document オブジェクトにテキストとファイル名メタデータを設定
            docs.append(Document(page_content=text, metadata={"source": fn}))
    return docs  # 読み込んだ PDF ドキュメントを返却

def load_texts() -> List[Document]:
    """
    DATA_FOLDER 配下の .txt および .csv ファイルをすべて読み込み、
    ファイル丸ごとのテキストを Document リストで返す
    """
    docs: List[Document] = []
    for fn in os.listdir(DATA_FOLDER):
        if fn.lower().endswith((".txt", ".csv")):
            path = os.path.join(DATA_FOLDER, fn)
            # テキストファイルを UTF-8 で読み込む
            with open(path, encoding="utf-8") as f:
                text = f.read()
            docs.append(Document(page_content=text, metadata={"source": fn}))
    return docs  # 読み込んだテキスト/CSV ドキュメントを返却

def load_all_documents() -> List[Document]:
    """
    上記の各ロード関数を順に呼び出し、すべての Document をまとめて返す
    """
    return (
        load_pdfs() + load_texts()
    )

if __name__ == "__main__":
    # モジュール単体実行時のテスト用処理
    docs = load_all_documents()  # すべてのドキュメントを読み込む
    print(f"Loaded {len(docs)} documents.")  # 読み込んだ件数を表示
    for doc in docs:
        # Document の metadata.source を表示
        print(doc.metadata.get("source"))
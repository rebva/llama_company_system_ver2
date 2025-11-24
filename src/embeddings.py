"""
ベクトルストア構築モジュール
- langchain.schema.Document の metadata.source を分割後も維持
- テキスト分割 → 埋め込み生成 → ChromaDB へ登録
"""
import chromadb  # ChromaDB クライアントライブラリをインポート
from langchain_community.vectorstores import Chroma  # LangChain 向け Chroma ベクトルストアラッパー
from langchain_huggingface import HuggingFaceEmbeddings  # Hugging Face 埋め込みモデルラッパー
from langchain_text_splitters import RecursiveCharacterTextSplitter  # テキストをチャンク分割するユーティリティ
from typing import List  # 型ヒント用

from src.config import CHROMA_DB_PATH  # ChromaDB の永続化ディレクトリ設定を読み込む
from src.loaders import load_all_documents  # 各種ファイルを Document リストとして読み込む関数

def build_vectorstore(persist: bool = True) -> Chroma:
    """
    ベクトルストアの構築を行う関数
    :param persist: 永続化を行うかどうか
    :return: 登録済みの Chroma インスタンス
    """
    # 1) Document オブジェクトをすべて読み込む
    docs: List[Document] = load_all_documents()

    # 2) テキストを指定文字数ごとにチャンク化する設定を作成
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,      # 各チャンクの最大文字数
        chunk_overlap=50     # 隣接チャンクの重複文字数
    )
    # 実際にドキュメントリストをチャンクに分割
    split_docs = splitter.split_documents(docs)

    # 3) 埋め込みモデルを初期化
    emb_model = HuggingFaceEmbeddings(
        model_name="sonoisa/sentence-bert-base-ja-mean-tokens-v2",  # 日本語Sentence-BERTモデル
        show_progress=True,                                         # 進捗バーを表示
        encode_kwargs={"batch_size": 32}                           # バッチサイズ設定
    )

    # 4) ChromaDB にチャンク化したドキュメントを登録
    vectordb = Chroma.from_documents(
        documents=split_docs,             # 登録するチャンクドキュメントリスト
        embedding=emb_model,              # 埋め込み生成用モデル
        persist_directory=CHROMA_DB_PATH   # データ永続化先ディレクトリ
    )
    # 永続化フラグが有効ならデータを保存（Chroma.from_documents 内で自動実行）
    return vectordb

if __name__ == "__main__":
    # このファイルを直接実行したときの処理
    db = build_vectorstore()  # ベクトルストア構築を実行
    print("Vectorstore built and persisted.")  # 完了メッセージ出力

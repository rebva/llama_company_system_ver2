from typing import List, Optional

import json
import os

from janome.tokenizer import Tokenizer

from langchain.chains import RetrievalQA  # RetrievalQAチェーンを使った質問応答機能
from langchain_community.llms import Ollama   # OllamaローカルLLMラッパー
from langchain_huggingface import HuggingFaceEmbeddings  # Hugging Face埋め込みモデルラッパー
from langchain_chroma import Chroma  # vectordbをインポートする際のChromaモジュール

from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from src.config import OLLAMA_MODEL, CHROMA_DB_PATH  # モデル名とChromaDBパス設定を取得


# ===== ハイブリッド用リトリーバー =====
class HybridRetriever(BaseRetriever):
    """
    ベクトル検索(意味検索) + BM25(全文検索) をまとめて扱うリトリーバー。
    RetrievalQA からは「ふつうの retriever」として見える。
    """

    def __init__(
        self,
        vector_retriever: BaseRetriever,
        bm25_retriever: BM25Retriever,
        tokenizer: Optional[Tokenizer] = None,
    ) -> None:
        super().__init__()
        self.vector_retriever = vector_retriever
        self.bm25_retriever = bm25_retriever
        self.tokenizer = tokenizer or Tokenizer()

    # LangChain v0.3系では _get_relevant_documents を実装する
    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager=None,
    ) -> List[Document]:
        # 1) ベクトル検索（意味検索）
        vector_docs = self.vector_retriever.get_relevant_documents(query)

        # 2) BM25用に質問をトークン化
        tokenized_query = self._tokenize_question(query)
        bm25_docs = self.bm25_retriever.get_relevant_documents(tokenized_query)

        # 3) BM25側で「original_text」があれば元に戻す
        restored_docs: List[Document] = []
        for doc in bm25_docs:
            original_text = doc.metadata.get("original_text", doc.page_content)
            restored_docs.append(
                Document(page_content=original_text, metadata=doc.metadata)
            )

        # 4) 2つの結果をマージ (merge: 結合) し、重複を削る
        merged: dict[str, Document] = {}
        for doc in vector_docs + restored_docs:
            key = doc.page_content
            if key not in merged:
                merged[key] = doc

        return list(merged.values())

    def _tokenize_question(self, text: str) -> str:
        """日本語クエリをBM25用にスペース区切りにする。"""
        tokens = [token.surface for token in self.tokenizer.tokenize(text)]
        return " ".join(tokens)


def _build_bm25_retriever() -> Optional[BM25Retriever]:
    """
    bm25_documents.json があれば BM25Retriever を作る。
    なければ None を返す（その場合は意味検索だけで動く）。
    """
    bm25_json_path = os.path.join(CHROMA_DB_PATH, "bm25_documents.json")

    if not os.path.exists(bm25_json_path):
        # BM25用のデータがない場合はスキップ
        return None

    with open(bm25_json_path, "r", encoding="utf-8") as f:
        bm25_data = json.load(f)

    bm25_documents = [
        Document(page_content=item["text"], metadata=item.get("metadata", {}))
        for item in bm25_data
    ]

    # k=3 はお好みで調整（top3 を返す）
    bm25_retriever = BM25Retriever.from_documents(bm25_documents, k=3)
    return bm25_retriever


def get_qa_chain() -> RetrievalQA:
    # 1) 埋め込みモデルを初期化: ドキュメント検索時に使用する
    emb_model = HuggingFaceEmbeddings(
        model_name="sonoisa/sentence-bert-base-ja-mean-tokens-v2"
    )

    # 2) 永続化されたChromaDBをロード: 既存のベクトルデータを再利用（意味検索担当）
    vectordb = Chroma(
        persist_directory=CHROMA_DB_PATH,  # DBファイルの格納先（ディレクトリ）
        embedding_function=emb_model       # 埋め込み関数として設定
    )

    # ベクトル検索用リトリーバー
    vector_retriever = vectordb.as_retriever(
        search_kwargs={"k": 3}  # 上位3チャンクを検索（必要に応じて調整）
    )

    # 3) BM25全文検索用リトリーバーを構築
    bm25_retriever = _build_bm25_retriever()

    # 4) リトリーバーの選択
    if bm25_retriever is not None:
        # ハイブリッド検索: 意味検索 + 全文検索
        retriever: BaseRetriever = HybridRetriever(
            vector_retriever=vector_retriever,
            bm25_retriever=bm25_retriever,
        )
    else:
        # フォールバック: BM25データがなければ意味検索だけ
        retriever = vector_retriever

    # 5) OllamaローカルLLMを初期化: 指定モデルを読み込む
    llm = Ollama(model=OLLAMA_MODEL,
                base_url=os.getenv("OLLAMA_HOST", "http://ollama_rebva:11434"))

    # 6) RetrievalQAチェーンを構築
    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,                   # 使用するLLM
        chain_type="stuff",        # チェーンの組み立て方式
        retriever=retriever,       # ここが「ハイブリッドリトリーバー」になる
        return_source_documents=True  # ソースドキュメントを結果に含める
    )

    return qa_chain  # 質問応答チェーンを返却


if __name__ == "__main__":
    # スクリプト単体実行時: QAチェーンを初期化して完了メッセージを表示
    qa = get_qa_chain()
    print("Hybrid RAG chain is ready.")

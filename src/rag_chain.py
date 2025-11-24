# src/rag_chain.py

import os
from typing import Dict, Any, List

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.llms import Ollama
from langchain_core.documents import Document

from src.config import CHROMA_DB_PATH, OLLAMA_MODEL

# ここで Ollama の URL を一元管理する
# OLLAMA_HOST 環境変数 (environment variable(環境変数)) があればそれを使う
# なければ "http://localhost:11434" を使う
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")


class SimpleRAG:
    """
    とてもシンプルな RAG クラス。
    retriever (Chroma) と llm (Ollama) を使って

        invoke({"query": "...", "user_id": "...", "role": "..."})

    の形で呼び出すと、

        {
            "result": "回答テキスト",
            "source_documents": [Document, ...]
        }

    を返す。
    """

    def __init__(self, llm, retriever):
        self.llm = llm
        self.retriever = retriever

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        # 1) クエリを取り出す
        query: str = inputs.get("query", "")

        # 2) 関連ドキュメントを取得
        # langchain 1.x の retriever は .invoke(query) でOK
        docs: List[Document] = self.retriever.invoke(query)

        # 3) ドキュメントを1つのテキストに結合
        context_text = "\n\n".join(d.page_content for d in docs)

        # 4) LLM へのプロンプトを作成
        prompt = f"""あなたはRAGシステムのアシスタントです。
以下のドキュメントに基づいて、ユーザーの質問に日本語で回答してください。
もしドキュメントに答えがない場合は、「手元の資料には答えがありません」と正直に伝えてください。

# 質問
{query}

# 参照ドキュメント
{context_text}
"""

        # 5) Ollama 経由で LLM を呼び出す
        answer: str = self.llm.invoke(prompt)

        # 6) RetrievalQA と似た形式で返す
        return {
            "result": answer,
            "source_documents": docs,
        }


def get_qa_chain() -> SimpleRAG:
    """
    - 埋め込みモデル
    - Chroma ベクトルストア
    - retriever
    - Ollama LLM

    を初期化して SimpleRAG を返す。
    """

    # 1) 埋め込みモデル (embedding(意味ベクトル化))
    emb_model = HuggingFaceEmbeddings(
        model_name="sonoisa/sentence-bert-base-ja-mean-tokens-v2"
    )

    # 2) 永続化された Chroma DB をロード
    vectordb = Chroma(
        persist_directory=CHROMA_DB_PATH,
        embedding_function=emb_model,
    )

    retriever = vectordb.as_retriever(
        search_kwargs={"k": 7}
    )

    # 3) Ollama LLM
    llm = Ollama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_HOST,
    )

    # 4) SimpleRAG を返す
    return SimpleRAG(llm=llm, retriever=retriever)


if __name__ == "__main__":
    qa = get_qa_chain()
    print("SimpleRAG chain is ready.")

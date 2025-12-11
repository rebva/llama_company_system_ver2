import json
import os
from functools import lru_cache
from typing import List, Optional

from janome.tokenizer import Tokenizer
from langchain.chains import RetrievalQA
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import OpenAI

from src.config import CHROMA_DB_PATH, LLM_MODEL, VLLM_BASE_URL

DEFAULT_TENANT_ID = "default"


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
        *,
        visibility_allowed: Optional[List[str]] = None,
        tenant_id: str = DEFAULT_TENANT_ID,
        tokenizer: Optional[Tokenizer] = None,
    ) -> None:
        super().__init__()
        self.vector_retriever = vector_retriever
        self.bm25_retriever = bm25_retriever
        self.visibility_allowed = visibility_allowed or []
        self.tenant_id = tenant_id
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
        vector_docs = self._filter_docs(vector_docs)

        # 2) BM25用に質問をトークン化
        tokenized_query = self._tokenize_question(query)
        bm25_docs = self.bm25_retriever.get_relevant_documents(tokenized_query)
        bm25_docs = self._restore_bm25_text(bm25_docs)
        bm25_docs = self._filter_docs(bm25_docs)

        # 3) 2つの結果をマージ (merge: 結合) し、重複を削る
        merged: dict[str, Document] = {}
        for doc in vector_docs + bm25_docs:
            key = doc.page_content
            if key not in merged:
                merged[key] = doc

        return list(merged.values())

    def _restore_bm25_text(self, bm25_docs: List[Document]) -> List[Document]:
        restored_docs: List[Document] = []
        for doc in bm25_docs:
            original_text = doc.metadata.get("original_text", doc.page_content)
            restored_docs.append(
                Document(page_content=original_text, metadata=doc.metadata)
            )
        return restored_docs

    def _filter_docs(self, docs: List[Document]) -> List[Document]:
        """visibility/tenant_id で絞り込む（後方互換のため None も許容）。"""
        allowed_vis = set(self.visibility_allowed or [])
        filtered: List[Document] = []
        for doc in docs:
            meta = getattr(doc, "metadata", {}) or {}
            visibility = meta.get("visibility")
            tenant_id = meta.get("tenant_id")

            if allowed_vis and visibility not in allowed_vis:
                continue
            if tenant_id not in (None, self.tenant_id):
                continue

            filtered.append(doc)
        return filtered

    def _tokenize_question(self, text: str) -> str:
        """日本語クエリをBM25用にスペース区切りにする。"""
        tokens = [token.surface for token in self.tokenizer.tokenize(text)]
        return " ".join(tokens)


def _visibility_allowed_for_role(role: str) -> List[str]:
    """role ごとの visibility 許可リスト（移行期は None を許可）。"""
    # Chroma のバリデーションに合わせて None は含めない
    if role == "admin":
        return ["public", "admin_only"]
    return ["public"]


def _visibility_from_filter(filter_kwargs: Optional[dict]) -> Optional[List[str]]:
    """既存の filter_kwargs から visibility 設定を抽出する。"""
    if not filter_kwargs:
        return None

    def _extract(vis_filter):
        if isinstance(vis_filter, dict):
            vals = vis_filter.get("$in")
            if isinstance(vals, list):
                return vals
        elif isinstance(vis_filter, list):
            return vis_filter
        return None

    if "$and" in filter_kwargs:
        clauses = filter_kwargs.get("$and") or []
        for clause in clauses:
            if not isinstance(clause, dict):
                continue
            if "visibility" in clause:
                extracted = _extract(clause["visibility"])
                if extracted is not None:
                    return extracted
        return None

    if "visibility" in filter_kwargs:
        return _extract(filter_kwargs["visibility"])

    return None


def _tenant_from_filter(filter_kwargs: Optional[dict]) -> Optional[str]:
    """filter_kwargs から tenant_id を抽出する。"""
    if not filter_kwargs:
        return None

    if "$and" in filter_kwargs:
        clauses = filter_kwargs.get("$and") or []
        for clause in clauses:
            if not isinstance(clause, dict):
                continue
            if "tenant_id" in clause:
                tenant = clause["tenant_id"]
                if isinstance(tenant, dict):
                    return tenant.get("$eq")
                return tenant
        return None

    tenant = filter_kwargs.get("tenant_id")
    if isinstance(tenant, dict):
        return tenant.get("$eq")
    return tenant


def _make_where_filter(*, tenant_id: str, visibility_in: List[str]) -> dict:
    """Chroma validate_where に沿った $and ラップ済みフィルタを作成する。"""
    cleaned_visibility = [v for v in visibility_in if v is not None]
    return {
        "$and": [
            {"tenant_id": {"$eq": tenant_id}},
            {"visibility": {"$in": cleaned_visibility}},
        ]
    }


@lru_cache(maxsize=1)
def _get_bm25_retriever() -> Optional[BM25Retriever]:
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


@lru_cache(maxsize=1)
def get_vectorstore() -> Chroma:
    """Chroma インスタンスを1回だけ作る（キャッシュ）。"""
    embeddings = HuggingFaceEmbeddings(
        model_name="sonoisa/sentence-bert-base-ja-mean-tokens-v2"
    )

    vectorstore = Chroma(
        embedding_function=embeddings,
        persist_directory=CHROMA_DB_PATH,
        collection_name="rag_documents",
    )

    return vectorstore


def build_vector_retriever_for_role(role: str) -> BaseRetriever:
    """role ("admin" / "user") に応じて filter を切り替える retriever を返す。"""
    vectorstore = get_vectorstore()
    visibility_allowed = _visibility_allowed_for_role(role)
    where_filter = _make_where_filter(
        tenant_id=DEFAULT_TENANT_ID,
        visibility_in=visibility_allowed,
    )

    retriever = vectorstore.as_retriever(
        search_kwargs={
            "k": 3,
            "filter": where_filter,
        }
    )
    return retriever


@lru_cache(maxsize=10)
def get_llm() -> OpenAI:
    """
    Completion ベースの LLM クライアントをキャッシュする。
    chat_template を避けるため /v1/completions を使う。
    """
    return OpenAI(
        base_url=VLLM_BASE_URL,
        model=LLM_MODEL,
        api_key=os.getenv("OPENAI_API_KEY", "dummy"),
        temperature=0,
    )


def _build_retriever(role: str, *, filter_kwargs: Optional[dict] = None) -> BaseRetriever:
    if filter_kwargs:
        vectorstore = get_vectorstore()
        tenant_id = _tenant_from_filter(filter_kwargs) or DEFAULT_TENANT_ID
        vis_from_filter = _visibility_from_filter(filter_kwargs) or []

        if "$and" in filter_kwargs:
            where_filter = filter_kwargs
        elif "tenant_id" in filter_kwargs or "visibility" in filter_kwargs:
            where_filter = _make_where_filter(
                tenant_id=tenant_id,
                visibility_in=vis_from_filter or _visibility_allowed_for_role(role),
            )
        else:
            where_filter = filter_kwargs

        search_kwargs = {"k": 3, "filter": where_filter}
        vector_retriever = vectorstore.as_retriever(search_kwargs=search_kwargs)
        visibility_allowed = vis_from_filter
    else:
        vector_retriever = build_vector_retriever_for_role(role)
        visibility_allowed = _visibility_allowed_for_role(role)
        tenant_id = DEFAULT_TENANT_ID

    bm25_retriever = _get_bm25_retriever()
    if bm25_retriever is not None:
        return HybridRetriever(
            vector_retriever=vector_retriever,
            bm25_retriever=bm25_retriever,
            visibility_allowed=visibility_allowed,
            tenant_id=tenant_id,
        )

    return vector_retriever


@lru_cache(maxsize=10)
def get_rag_chain(role: str) -> RetrievalQA:
    """
    roleごとに別のRAGチェーンを作ってキャッシュする。
    """
    retriever = _build_retriever(role)

    qa = RetrievalQA.from_chain_type(
        llm=get_llm(),
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True,
    )
    return qa


def get_qa_chain(filter_kwargs: Optional[dict] = None) -> RetrievalQA:
    """
    互換用のエントリポイント。filter_kwargs 指定時はそのまま使用し、
    それ以外はユーザー権限でのチェーンを返す。
    """
    if filter_kwargs:
        retriever = _build_retriever("user", filter_kwargs=filter_kwargs)
        return RetrievalQA.from_chain_type(
            llm=get_llm(),
            chain_type="stuff",
            retriever=retriever,
            return_source_documents=True,
        )

    return get_rag_chain("user")


if __name__ == "__main__":
    # スクリプト単体実行時: QAチェーンを初期化して完了メッセージを表示
    qa = get_rag_chain("user")
    print("Hybrid RAG chain is ready.")

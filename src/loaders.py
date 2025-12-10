"""
ドキュメントローダー
- rag_data/public と rag_data/admin_only を走査して Document を返す
- 各チャンクにアクセス制御用のメタデータを付与する
"""
from pathlib import Path
from typing import List

from langchain_community.document_loaders import CSVLoader, PyPDFLoader, TextLoader
from langchain.schema import Document

from src.config import DATA_FOLDER

# ベースディレクトリ
DATA_FOLDER_PATH = Path(DATA_FOLDER)
PUBLIC_FOLDER = DATA_FOLDER_PATH / "public"
ADMIN_ONLY_FOLDER = DATA_FOLDER_PATH / "admin_only"

# メタデータのデフォルト値
DEFAULT_TENANT_ID = "default"
PUBLIC_ROLES = ["admin", "user"]
ADMIN_ROLES = ["admin"]


def load_folder(folder: Path) -> List[Document]:
    """1つのフォルダ内の .pdf / .txt / .md / .csv を全部読む。"""
    docs: List[Document] = []

    for path in folder.rglob("*"):
        if path.is_dir():
            continue

        suffix = path.suffix.lower()
        if suffix == ".pdf":
            loader = PyPDFLoader(str(path))
        elif suffix in [".txt", ".md"]:
            loader = TextLoader(str(path), encoding="utf-8")
        elif suffix == ".csv":
            loader = CSVLoader(str(path))
        else:
            # unsupported (対応していない) 拡張子はスキップ
            continue

        docs.extend(loader.load())

    return docs


def _apply_metadata(docs: List[Document], *, visibility: str, roles_allowed: List[str], default_source: Path) -> None:
    """metadata を壊さないように付与・補完する。"""
    for doc in docs:
        doc.metadata = doc.metadata or {}
        existing_source = doc.metadata.get("source") or doc.metadata.get("file_path")
        doc.metadata.setdefault("source", str(existing_source or default_source))
        doc.metadata["visibility"] = visibility
        # Chromaはメタデータに配列を許容しないため文字列で保持する
        doc.metadata["roles_allowed"] = ",".join(roles_allowed)
        doc.metadata["tenant_id"] = DEFAULT_TENANT_ID


def load_all_documents() -> List[Document]:
    """public / admin_only を読み込み、visibility を設定して返す。"""
    all_docs: List[Document] = []

    if PUBLIC_FOLDER.exists():
        public_docs = load_folder(PUBLIC_FOLDER)
        _apply_metadata(
            public_docs,
            visibility="public",
            roles_allowed=PUBLIC_ROLES,
            default_source=PUBLIC_FOLDER,
        )
        all_docs.extend(public_docs)

    if ADMIN_ONLY_FOLDER.exists():
        admin_docs = load_folder(ADMIN_ONLY_FOLDER)
        _apply_metadata(
            admin_docs,
            visibility="admin_only",
            roles_allowed=ADMIN_ROLES,
            default_source=ADMIN_ONLY_FOLDER,
        )
        all_docs.extend(admin_docs)

    return all_docs


if __name__ == "__main__":
    docs = load_all_documents()
    print(f"Loaded {len(docs)} documents.")
    for doc in docs:
        print(doc.metadata.get("source"))

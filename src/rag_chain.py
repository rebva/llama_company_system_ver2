from langchain.chains import RetrievalQA  # RetrievalQAチェーンを使った質問応答機能
from langchain_community.llms import Ollama   # OllamaローカルLLMラッパー
from langchain_huggingface import HuggingFaceEmbeddings  # Hugging Face埋め込みモデルラッパー
# vectordbをインポートする際のChromaモジュール
from langchain_chroma import Chroma
from src.config import OLLAMA_MODEL, CHROMA_DB_PATH  # モデル名とChromaDBパス設定を取得

from dotenv import load_dotenv
import os  # os を利用して環境変数読み込み
load_dotenv()
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:8080')
def get_qa_chain() -> RetrievalQA:
    # 1) 埋め込みモデルを初期化: ドキュメント検索時に使用する
    emb_model = HuggingFaceEmbeddings(
        model_name="sonoisa/sentence-bert-base-ja-mean-tokens-v2"
    )

    # 2) 永続化されたChromaDBをロード: 既存のベクトルデータを再利用
    vectordb = Chroma(
        persist_directory=CHROMA_DB_PATH,  # DBファイルの格納先
        embedding_function=emb_model          # 埋め込み関数として設定
    )

    # 3) OllamaローカルLLMを初期化: 指定モデルを読み込む
    llm = Ollama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_HOST,
        )

    # 4) RetrievalQAチェーンを構築
    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,                         # 使用するLLM
        chain_type="stuff",            # チェーンの組み立て方式
        retriever=vectordb.as_retriever(
            search_kwargs={"k": 7}    # 上位7チャンクを検索
        ),
        return_source_documents=True    # ソースドキュメントを結果に含める
    )

    return qa_chain  # 質問応答チェーンを返却

if __name__ == "__main__":
    # スクリプト単体実行時: QAチェーンを初期化して完了メッセージを表示
    qa = get_qa_chain()
    print("RAG chain is ready.")
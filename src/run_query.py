import sys  # コマンドライン引数や終了コード制御用
from src.rag_chain import get_qa_chain  # RetrievalQAチェーン構築関数をインポート

def main(question: str):
    # 1) RetrievalQAチェーンを取得
    qa = get_qa_chain()
    # 2) invokeメソッドでクエリを実行（辞書形式で引数を渡す）
    result = qa.invoke({"query": question})

    # 回答部分をコンソールに出力
    print("\n===== 回答 =====")
    print(result.get("result"))  # 'result'キーに回答テキストが格納されている

    # ソースドキュメント一覧の出力
    print("\n===== 参照ドキュメント =====")
    for doc in result.get("source_documents", []):
        # メタデータからsource（ファイル名）を取得
        source = doc.metadata.get("source", "unknown")
        # ドキュメント内容の冒頭50文字をスニペットとして整形
        snippet = doc.page_content.replace("\n", " ")[:50]
        # ファイル名とスニペットを表示
        print(f"- {source}: …{snippet}…")

if __name__ == "__main__":
    # 引数チェック: 質問が渡されていない場合は使用方法を表示して終了
    if len(sys.argv) < 2:
        print("Usage: python -m src.run_query \"質問文をここに書く\"")
        sys.exit(1)
    # コマンドライン第1引数を質問として main() を呼び出し
    main(sys.argv[1])

"""
事前準備用スクリプト
- ドキュメント読み込み（PDF / テキスト / CSV）
- メタデータ付与
- テキスト分割と埋め込み生成
- ChromaDBへの登録（永続化）
"""
import sys  # システム操作用（exit処理）

from src.embeddings import build_vectorstore  # ベクトルストア構築関数
from src.loaders import load_all_documents  # ドキュメント読み込み関数


def main():
    """
    事前準備処理:
    1) ドキュメントをロード（visibility 等のメタデータ付与込み）
    2) ベクトルストアを構築・永続化
    3) 完了メッセージ表示
    """
    try:
        # ステップ1: ドキュメント読み込み開始
        print("[1/3] ドキュメントを読み込んでいます...")
        docs = load_all_documents()
        print(f"    読み込んだドキュメント数: {len(docs)}")

        # ステップ2: ベクトルストア構築開始
        print("[2/3] ベクトルストアの構築を開始しています...")
        build_vectorstore(docs=docs, persist=True)
        print("    ベクトルストアの永続化が完了しました。")

        # ステップ3: 全体完了
        print("[3/3] 事前準備が完了しました。次は run_query.py を使って質問応答を実行できます。")
    except Exception as e:
        # エラー発生時: エラーメッセージを出力してプロセスを終了
        print(f"[エラー] 事前準備中に例外が発生しました: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # このスクリプトが単体実行された場合、main 関数を呼び出す
    main()

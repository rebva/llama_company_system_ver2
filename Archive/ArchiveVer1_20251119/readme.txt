未実装要件
    履歴をmain.pyで管理
        データベースは未実装
    X-User-Idをヘッダで使用(JWT未使用)
        暗号化されていない
実装済み要件
    OLLAMAはdockerで動作
    docker network のgarak-netで接続
    portは8080:8080で接続

cd ~/docker/LlmApi/ArchiveVer1_20251119

# 念のため再ビルド
docker compose build

# 起動
docker compose up -d

# 状態確認
docker compose ps

curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: CHANGE_ME" \
  -H "X-User-Id: eguchi" \
  -d '{
    "message": "Hello from docker api",
    "session_id": "test1"
  }'



未実装要件
    
実装済み要件
    履歴をSQliteで管理
    JWT認証
        base64で暗号化(容易に復号可能)

    OLLAMAはdockerで動作
        docker network のgarag-netで接続
        portは8080:8080で接続

cd ~/docker/LlmApi/ArchiveVer2_20251119

docker compose down
docker compose build
docker compose up -d
docker compose ps


curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: CHANGE_ME" \
  -H "X-User-Id: eguchi" \
  -d '{
    "message": "First message",
    "session_id": "session-db-test"
  }'


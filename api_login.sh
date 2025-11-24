
# TOKENを環境変数として設定
# 1) ログインしてトークン取得
TOKEN=$(curl -s -X POST http://localhost:8080/login \
	-H "Content-Type: application/json" \
	-d '{"username":"user1","password":"user1"}' | jq -r '.access_token')


echo $TOKEN

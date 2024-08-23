from flask import Flask, request, abort
from linebot.v3.webhook import (
    WebhookHandler
)

from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)

from linebot.models import (
    TextSendMessage
)

import config, database
from cohere import Client
from cohere import Message_User
from cohere import Message_Chatbot
from cohere import ChatConnector
import schedule
import time
import threading
import requests
import sqlite3

app = Flask(__name__)

co = Client(client_name="command-r-plus", api_key="y9twkpdMHbOTnW9ovXJmBQU3rwCI5NGsHVk2t88d", )

configuration = Configuration(access_token=config.CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(config.CHANNEL_SECRET)

@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        
        linebot_api = MessagingApi(api_client)
        
        responce = co.chat(
            message=event.message.text,
            chat_history=[
                Message_User(message="あなたはキャンプについて詳しい人です。キャンプについての質問のみ答えてください。それ以外の質問は回答を拒否してください。"),
            ],
            connectors=[ChatConnector(id="web-search")],
        )
        
        reply_text = responce.text # ユーザーから送られたテキストを取得
        linebot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)] 
            )
        )
        

if __name__ == "__main__":
    app.run(port=8080)
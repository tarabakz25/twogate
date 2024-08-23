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
        
        #キャンプ場を調べる
        if event.message.text == "きゃんぷ場調べ":
            send_message(event, "調べたい地域は？")
            
            # ユーザーの返答を待機
            region = None
            while region is None:
                @handler.add(MessageEvent, message=TextMessageContent)
                def handle_region(event):
                    nonlocal region
                    region = event.message.text
            
            send_message(event, "行きたい日にちは？")
            
            # 日付の入力を待機
            date = None
            while date is None:
                @handler.add(MessageEvent, message=TextMessageContent)
                def handle_date(event):
                    nonlocal date
                    date = event.message.text
            
            # ここで region と date を使用して次の処理を行う
            responce = co.chat(
                message=f"{region}の{date}に行きたいキャンプ場を調べてください。",
                chat_history=[
                    Message_Chatbot(message="調べた結果、以下の場所が見つかりました。"),
                ],
                connectors=[ChatConnector(id="web-search")],
            )
            
            send_message(event, responce.text)
            
        #野営地を調べる
        elif event.message.text == "野営地調べ":
            send_message(event, "調べたい地域は？")
            
            region = None
            while region is None:
                @handler.add(MessageEvent, message=TextMessageContent)
                def handle_region(event):
                    nonlocal region
                    region = event.message.text
            
            responce = co.chat(
                message=f"{region}が野営できる場所か、{region}のホームページから調べてください。",
                max_tokens=20,
            )
            
            send_message(event, responce.text)
            
        else:
            responce = co.chat(
            message=event.message.text,
            chat_history=[
                Message_User(message="あなたはキャンプについて詳しい人です。キャンプについての質問のみ答えてください。それ以外の質問は回答を拒否してください。"),
                ],
                connectors=[ChatConnector(id="web-search")],
            )
            
            send_message(event, responce.text)
        
        
def send_message(event, text):
    with ApiClient(configuration) as api_client:
        linebot_api = MessagingApi(api_client)

        linebot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=text)
        )
        

if __name__ == "__main__":
    app.run(port=8080)
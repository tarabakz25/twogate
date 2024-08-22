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

import config

app = Flask(__name__)

configuration = Configuration(access_tokenj=config.CHANNEL_ACCESS_TOKEN)
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
        linebot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token = event.reply.token,
                messages=[TextMessage(text=event.message.text)]
            )
        )
        
if __name__ == "__main__":
    app.run()
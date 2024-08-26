from flask import Flask, request, abort
from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage, FlexMessage, FlexContainer
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent
from linebot.v3.messaging import PushMessageRequest
import config
import json
from cohere import Client
from cohere import Message_User
from cohere import Message_Chatbot
from cohere import ChatConnector

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from urllib.parse import urlparse, urljoin
import subprocess
import os
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import threading

from linebot.models import TextSendMessage, FlexSendMessage
from linebot.models.messages import Message
from linebot.models.send_messages import SendMessage

import sqlite3

app = Flask(__name__)

co = Client(client_name="command-r-plus", api_key="y9twkpdMHbOTnW9ovXJmBQU3rwCI5NGsHVk2t88d")

configuration = Configuration(access_token=config.CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(config.CHANNEL_SECRET)

# ユーザーごとの状態を管理する辞書
user_state = {}

# スケジューラーの設定
scheduler = BackgroundScheduler()
scheduler.start()

# データベース接続とテーブル作成
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id TEXT PRIMARY KEY)''')
    conn.commit()
    conn.close()

# ユーザーIDを保存
def save_user_id(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

# 全ユーザーIDを取得
def get_all_user_ids():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    user_ids = [row[0] for row in c.fetchall()]
    conn.close()
    return user_ids

# アプリケーション起動時にデータベースを初期化
init_db()

@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    save_user_id(user_id)
    
    welcome_message = TextMessage(text="友達追加ありがとうございます！キャンプに関する情報をお届けします。")
    
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        reply_message_request = ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[welcome_message]
        )
        line_bot_api.reply_message(reply_message_request)
    
    print(f"新しいユーザーが追加されました: {user_id}")

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    save_user_id(user_id)
    text = event.message.text

    # ユーザーの状態をチェック
    if user_id not in user_state:
        if text == "きゃんぷ場調べ":
            user_state[user_id] = "awaiting_region_camp"
            send_message(event, "調べたい地域を教えてください。")
        elif text == "野営地調べ":
            user_state[user_id] = "awaiting_prefecture_yaychi"
            send_message(event, "野営したい都道府県を教えてください。")
        elif text == "持ち物提案":
            user_state[user_id] = "awaiting_location_items"
            send_message(event, "行く場所を教えてください。")
        else:
            handle_general_message(event, text)
    elif user_state[user_id] == "awaiting_location_items":
        user_state[user_id] = "awaiting_duration_items"
        user_state[user_id + "_location"] = text
        send_message(event, "滞在期間を教えてください。")
    elif user_state[user_id] == "awaiting_duration_items":
        user_state[user_id] = "awaiting_conditions_items"
        user_state[user_id + "_duration"] = text
        send_message(event, "その他の特別な条件があれば教えてください。（例：雨の可能性がある、子供連れ、など）")
    elif user_state[user_id] == "awaiting_conditions_items":
        location = user_state.pop(user_id + "_location")
        duration = user_state.pop(user_id + "_duration")
        conditions = text
        user_state.pop(user_id)
        handle_item_suggestion(user_id, location, duration, conditions)
    elif user_state[user_id] == "awaiting_region_camp":
        region = text
        user_state[user_id] = "awaiting_date_camp"
        user_state[user_id + "_region"] = region
        send_message(event, "行きたい日にちを教えてください。")
    elif user_state[user_id] == "awaiting_date_camp":
        date = text
        user_state[user_id] = "awaiting_conditions_camp"
        user_state[user_id + "_date"] = date
        send_message(event, "希望する条件はありますか？（例：ペットOK、温泉あり、など）")
    elif user_state[user_id] == "awaiting_conditions_camp":
        conditions = text
        region = user_state.pop(user_id + "_region")
        date = user_state.pop(user_id + "_date")
        user_state.pop(user_id)
        handle_camping_info(user_id, region, date, conditions)
    elif user_state[user_id] == "awaiting_prefecture_yaychi":
        prefecture = text
        user_state[user_id] = "awaiting_conditions_yaychi"
        user_state[user_id + "_prefecture"] = prefecture
        send_message(event, "希望する条件はありますか？（例：川の近く、山の中、など）")
    elif user_state[user_id] == "awaiting_conditions_yaychi":
        conditions = text
        prefecture = user_state.pop(user_id + "_prefecture")
        user_state.pop(user_id)
        handle_yaychi_info(user_id, prefecture, conditions)
    else:
        handle_general_message(event, text)

def send_message(event, text):
    with ApiClient(configuration) as api_client:
        linebot_api = MessagingApi(api_client)
        
        # メッセージオブジェクトを作成
        message = TextMessage(text=text)
        reply_message_request = ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[message]
        )
        linebot_api.reply_message(reply_message_request)

def send_push_message(user_id, text):
    with ApiClient(configuration) as api_client:
        linebot_api = MessagingApi(api_client)
        
        # メッセージを5000文ごとに分割
        messages = [text[i:i+5000] for i in range(0, len(text), 5000)]
        
        for message_text in messages:
            message = TextMessage(text=message_text)
            push_message_request = PushMessageRequest(to=user_id, messages=[message])
            linebot_api.push_message(push_message_request)
        
def send_flex_message(user_id, flex_message):
    with ApiClient(configuration) as api_client:
        linebot_api = MessagingApi(api_client)
        
        push_message_request = PushMessageRequest(to=user_id, messages=[flex_message])
        linebot_api.push_message(push_message_request)

def get_camp_info(camp_name):
    # web-search.pyを実行してURLを取得
    subprocess.run(["python", "web-search.py", camp_name], check=True)
    
    # first_link.txtからURLを読み取る
    homepage_url = ""
    if os.path.exists("first_link.txt"):
        with open("first_link.txt", "r") as file:
            homepage_url = file.read().strip()
    
    # URLが空の場合、デフォルト値を設定
    if not homepage_url:
        homepage_url = f"https://www.google.com/search?q={quote_plus(camp_name)}"

    return {
        'homepage_url': homepage_url,
        'image_url': "https://example.com/default-camp-image.jpg"  # デフォルトの画像URLを使用
    }

def parse_cohere_response(response_text):
    camp_info = []
    lines = response_text.split('\n')
    
    for line in lines:
        line = line.strip()
        if line and not line.startswith(('1.', '2.', '3.')):
            camp_info.append({'name': line})
    
    return camp_info[:3]  # 最大3つのキャンプ場情報を返す

def handle_camping_info(user_id, region, date, conditions):
    # 最初に即座に返信
    response_text = f"{region}の{date}に行きたいキャンプ場を、条件「{conditions}」で調べています..."
    send_push_message(user_id, response_text)
    
    # Cohereで追加の情報を取得
    res = co.chat(
        message=f"{region}の{date}で、条件「{conditions}」に合うキャンプ場を3つ調べて、名前のみをリストで教えてください。"
    )
    
    camp_info = parse_cohere_response(res.text)
    
    if not camp_info:
        error_message = f"申し訳ありません。キャンプ場の情報を取得できませんでした。\nCohere: {res.text}"
        send_push_message(user_id, error_message)
        return

    with open("flex_message.json", "r", encoding='utf-8') as file:
        flex_template = json.load(file)
    
    for i, camp in enumerate(camp_info):
        if i < len(flex_template['contents']):
            additional_info = get_camp_info(camp['name'])
            camp.update(additional_info)
            
            bubble = flex_template['contents'][i]
            bubble['body']['contents'][0]['text'] = camp['name']
            bubble['body']['contents'][1]['contents'][0]['contents'][0]['text'] = 'キャンプ場'
            bubble['footer']['contents'][0]['contents'][0]['action']['uri'] = camp.get('homepage_url', f"https://www.google.com/search?q={quote_plus(camp['name'])}")

    send_push_message(user_id, "以下のキャンプ場を見つけました！")
    
    flex_message = FlexMessage(alt_text="キャンプ場情報", contents=FlexContainer.from_dict(flex_template))
    send_flex_message(user_id, flex_message)
    
    res = co.chat(
        message=f"調べたキャンプ場の情報を{flex_message}に沿ってそれぞれ書いてください。内容は次の項目を書いてください。"
                "1.キャンプ場名"
                "2.市区町村"
                "3.キャンプ場設備"
                "またメッセージはこの形式以外書かないでください。"
    )
    
    send_push_message(user_id, res.text)
    

def handle_yaychi_info(user_id, prefecture, conditions):
    # 最初に即座に返信
    response_text = f"{prefecture}で、条件「{conditions}」に合う野営ができる場所を調べています..."
    send_push_message(user_id, response_text)
    
    # Cohere野営可能な市区町村とおすすめスポットを取得
    res = co.chat(
        message=f"{prefecture}で野営ができる市区町村を3つ調べて、条件「{conditions}」に合うものを選んでください。それぞれの市区町村について以下の情報を教えてください：\n"
                "1. 市区町村名\n"
                "2. おすすめの野営スポット\n"
                "3. そのスポットの特徴や注意点\n"
                "回答は以下のフォーマットで提供してください：\n"
                "1. [市区町村名]\n"
                "おすすめスポット: [スット]\n"
                "特徴・注意点: [簡単な説明]\n"
                "2. [次の市区町村名]\n"
                "...(同様に3つ目まで)\n",
        max_tokens=50,
    )
    
    yaychi_info = parse_yaychi_response(res.text)
    
    if not yaychi_info:
        error_message = f"申し訳ありません。野営地の情報を取得できませんでした。\nCohere: {res.text}"
        send_push_message(user_id, error_message)
        return

    with open("flex_message_yaychi.json", "r", encoding='utf-8') as file:
        flex_template = json.load(file)
    
    for i, info in enumerate(yaychi_info):
        if i < len(flex_template['contents']):
            bubble = flex_template['contents'][i]
            bubble['body']['contents'][0]['text'] = info['name']
            bubble['body']['contents'][1]['contents'][0]['contents'][1]['text'] = info['spot']
            bubble['body']['contents'][1]['contents'][1]['contents'][1]['text'] = info['description']

    send_push_message(user_id, f"{prefecture}で野営可能な場所が見つかりました！")
    
    flex_message = FlexMessage(alt_text="野営地情報", contents=FlexContainer.from_dict(flex_template))
    send_flex_message(user_id, flex_message)

def parse_yaychi_response(response_text):
    yaychi_info = []
    current_info = {}
    
    for line in response_text.split('\n'):
        line = line.strip()
        if line.startswith(('1.', '2.', '3.')):
            if current_info:
                yaychi_info.append(current_info)
            current_info = {'name': line[3:].strip()}
        elif 'おすすめスポット:' in line:
            current_info['spot'] = line.split('おすすめスポット:')[1].strip()
        elif '特徴・注意点:' in line:
            current_info['description'] = line.split('特徴・注意点:')[1].strip()
    
    if current_info:
        yaychi_info.append(current_info)
    
    return yaychi_info[:3]  # 最大3つの野営地情報を返す

def handle_item_suggestion(user_id, location, duration, conditions):
    response_text = f"{location}に{duration}の期間で行く際の持ち物を、条件「{conditions}」で提案します..."
    send_push_message(user_id, response_text)
    
    res = co.chat(
        message=f"{location}に{duration}の期間で行く際に必要な持ち物を、条件「{conditions}」を考慮して10個程度リストアップしてください。"
                "それぞれの持ち物について、20文字程度の簡潔な説明を加えてください。"
    )
    
    items = parse_item_response(res.text)
    
    if not items:
        error_message = f"申し訳ありません。持ち物の情報を取得できませんでした。\nCohere: {res.text}"
        send_push_message(user_id, error_message)
        return

    send_push_message(user_id, "以下の持ち物をおすすめします：\n\n" + "\n".join([f"- {item['name']}: {item['description']}" for item in items]))
    
    for item in items[:3]:
        search_query = f"{item['name']} おすすめ 人気"
        res = co.chat(
            message=f"「{search_query}」で検索し、評価の高いアイテムを1つ見つけて、その商品名と50文字以内の特徴を教えてください。"
        )
        send_push_message(user_id, f"{item['name']}のおすすめ商品：\n{res.text}")

def parse_item_response(response_text):
    items = []
    lines = response_text.split('\n')
    
    for line in lines:
        line = line.strip()
        if line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '10.')):
            parts = line.split(':', 1)
            if len(parts) == 2:
                name = parts[0].split('.', 1)[1].strip()
                description = parts[1].strip()
                items.append({'name': name, 'description': description})
    
    return items

def handle_general_message(event, text):
    res = co.chat(
        message=event.message.text,
        chat_history=[
            Message_User(message="あなたは'まるキャン'というキャンプの専門家です。キャンプや野営地の問に答えてください。それ以外の質問には回答しないようにしてください。文末には時々!をつけて、明るいイメージで会話してください。")
        ],
        max_tokens=60
    )
    send_message(event, res.text)

def fetch_camp_items():
    items = []
    res = co.chat(
        message="キャンプグッズのおすすめアイテムを3つ教えてください。それぞれ商品名と50文字以内の説明を含めてください。"
    )
    parsed_items = parse_daily_info(res.text)
    
    for item in parsed_items:
        search_query = f"{item['name']} キャンプ用品"
        url = get_first_search_result(search_query)
        items.append({
            'name': item['name'],
            'description': item['description'],
            'url': url
        })
    
    return items

def parse_daily_info(response_text):
    items = []
    lines = response_text.split('\n')
    for line in lines:
        if ':' in line:
            name, description = line.split(':', 1)
            items.append({'name': name.strip(), 'description': description.strip()})
    return items[:3]  # 最大3つのアイテムを返す

def get_first_search_result(query):
    search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(search_url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    first_result = soup.find('div', class_='yuRUbf')
    if first_result:
        url = first_result.find('a')['href']
        parsed_url = urlparse(url)
        if parsed_url.scheme and parsed_url.netloc:
            return url
    return "https://www.google.com/search?q=" + requests.utils.quote(query)  # デフォルトのURLを返す

def create_daily_flex_message(items):
    with open("flex_message_daily.json", "r", encoding='utf-8') as file:
        flex_template = json.load(file)
    
    for i, item in enumerate(items):
        if i < len(flex_template['contents']):
            bubble = flex_template['contents'][i]
            bubble['body']['contents'][0]['text'] = item['name']
            bubble['body']['contents'][1]['contents'][0]['contents'][1]['text'] = item['description']
            
            # URLの検証と修正
            url = item['url']
            parsed_url = urlparse(url)
            if not parsed_url.scheme:
                url = urljoin("https://", url)
            bubble['footer']['contents'][0]['action']['uri'] = url

    flex_container = FlexContainer.from_dict(flex_template)
    return FlexMessage(alt_text="本日のキャンプ情報", contents=flex_container)

def fetch_camp_items():
    items = []
    res = co.chat(
        message="キャンプグッズのおすすめアイテムを3つ教えてください。それぞれ商品名と50文字以内の説明を含めてください。"
    )
    parsed_items = parse_daily_info(res.text)
    
    for item in parsed_items:
        search_query = f"{item['name']} キャンプ用品"
        url = get_first_search_result(search_query)
        items.append({
            'name': item['name'],
            'description': item['description'],
            'url': url
        })
    
    return items

def send_daily_message():
    items = fetch_camp_items()  # アイテムを取得（URLを含む）
    flex_message = create_daily_flex_message(items)
    greeting = TextMessage(text="おはようございます！まるキャンです！\n今日のおすすめグッズの特集です。\n気になったものから見ていってください😊")
    
    user_ids = get_all_user_ids()
    
    if not user_ids:
        print("ユーザーIDが見つかりません。")
        return
    
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        
        for user_id in user_ids:
            try:
                push_message_request = PushMessageRequest(to=user_id, messages=[greeting, flex_message])
                line_bot_api.push_message(push_message_request)
                print(f"メッセージを送信しました: {user_id}")
            except Exception as e:
                print(f"ユーザー {user_id} へのメッセージ送信に失敗しました: {str(e)}")

# スケジューリングジョブの追加
scheduler.add_job(send_daily_message, 'cron', hour=9, minute=0)

def console_input():
    while True:
        command = input("コマンドを入力してください（'send' で配信メッセージを送信）: ")
        if command.lower() == 'send':
            send_daily_message()
            print("配信メッセージを送信しました。")

if __name__ == "__main__":
    # コンソール入力用のスレッドを開始
    input_thread = threading.Thread(target=console_input, daemon=True)
    input_thread.start()

    # Flaskアプリケーションを実行
    app.run(port=8080)
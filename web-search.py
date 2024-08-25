import requests
from bs4 import BeautifulSoup
import urllib.parse
import sys

def google_search(query):
    # 検索クエリをエンコード
    query = urllib.parse.quote(query)
    
    # Google検索のURLを生成
    url = f"https://www.google.com/search?q={query}"
    
    # ユーザーエージェントを設定してリクエストを送信
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    
    # ステータスコードを確認
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 検索結果のリンクを取得
        for g in soup.find_all('div', class_='g'):
            link = g.find('a', href=True)
            if link:
                first_link = link['href']
                # リンクをファイルに保存
                with open("first_link.txt", "w") as file:
                    file.write(first_link)
                break
    else:
        print("Google検索のリクエストに失敗しました。", file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        search_query = sys.argv[1]
        google_search(search_query)
    else:
        print("検索クエリを指定してください。", file=sys.stderr)
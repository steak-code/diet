import os
import requests
from bs4 import BeautifulSoup

import random
import logging

from flask import Flask, request, abort
from werkzeug.middleware.proxy_fix import ProxyFix

from linebot.v3 import (
    WebhookHandler
)

from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    TemplateMessage,
    CarouselTemplate,
    CarouselColumn,
    ImageCarouselTemplate,
    ImageCarouselColumn,
    MessageAction,
    URIAction
)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1, x_proto=1)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
app.logger.setLevel(logging.INFO)

line_channel_secret = os.getenv('line_channel_secret')
line_channel_access_token = os.getenv('line_channel_access_token')

handler = WebhookHandler(line_channel_secret)

configuration = Configuration(
    access_token=line_channel_access_token
)

@app.route("/", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']

    body = request.get_data(as_text=True)
    print("BODY: ", body)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'

base_url = "https://www.7-11.com.tw/freshfoods/read_food_xml_hot.aspx?="
category_mapping = {
    "ricerolls": "1_Ricerolls",
    "sandwich": "16_sandwich",
    "light": "2_Light",
    "cuisine": "3_Cuisine",
    "Snacks": "4_Snacks",
    "ForeignDishes": "5_ForeignDishes",
    "Noodles": "6_Noodles",
    "Oden": "7_Oden",
    "Bigbite": "8_Bigbite",
    "bread": "11_bread",
    "luwei": "13_luwei",
    "ohlala": "17_ohlala",
    "veg": "18_veg",
    "star": "19_star",
    "ice": "22_ice"
}
urls = [base_url + str(i) for i in [0, 1, 2, 3, 4, 5, 6, 7, 8, 11, 14, 16, 17, 18, 21]]

def scrape_url(url):
    header_info = {'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    res = requests.get(url, headers=header_info)
    soup = BeautifulSoup(res.text, 'html.parser')
    items = soup.find_all("item")
    results = []
    for item in items:
        name = item.find("name").text.strip() if item.find("name") else None
        itype = item.get("itype")
        sdate = item.find_next("sdate").text.strip() if item.find_next("sdate") else None
        if itype and sdate:
            image_elem = item.find('image')
            image_path = image_elem.text if image_elem.text else image_elem.next_sibling.strip()
            category_prefix = next((category_mapping[key] for key in category_mapping if key in image_path), None)
            image = f"https://www.7-11.com.tw/freshfoods/{category_prefix}/{image_path}" if category_prefix else None
            results.append({"name": name, "image": image})
    return results

def categorize_foods(food_items):
    categories = {
        "醣類": ["奶", "果", "飯", "饅頭", "包子", "飯糰", "麵包", "米", "麵", "蛋糕"],
        "蛋白質": ["魚", "蝦", "肉", "起司", "淇淋", "奶", "雞", "牛", "豬", "蛋", "豆腐", "豆", "鴨", "鵝", "腸", "腿"],
        "脂質": ["油", "雞", "牛", "豬", "鴨", "鵝", "肥", "腸", "腿"],
        "維生素": ["蘿蔔", "瓜", "水果", "蔬", "菜", "果"],
        "礦物質": ["牛奶", "芝麻", "穀", "堅果", "貝", "豆", "蔬", "菜"]
    }
    
    categorized_results = {key: [] for key in categories}

    for item in food_items:
        added = False
        for category, keywords in categories.items():
            if any(keyword in item["name"].lower() for keyword in keywords):
                categorized_results[category].append(item)
                added = True
        if not added:
            categorized_results.setdefault("其他", []).append(item)

    return categorized_results

all_scraped_data = []
for url in urls:
    scraped_data = scrape_url(url)
    all_scraped_data.extend(scraped_data)

categorized_foods = categorize_foods(all_scraped_data)

def clean_categorized_foods(categorized_foods):
    for category, foods in categorized_foods.items():
        categorized_foods[category] = [
            food for food in foods 
            if len(food["name"]) <= 12 and food["image"] is not None
        ]
    return categorized_foods

cleaned_categorized_foods = clean_categorized_foods(categorized_foods)

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        if text == "飲食搜索":
            carousel_columns = [
                CarouselColumn(
                    title='飲食搜索',
                    text='請選擇分類',
                    actions=[
                        MessageAction(label='醣類', text='醣類'),
                        MessageAction(label='脂質', text='脂質'),
                        MessageAction(label='蛋白質', text='蛋白質')
                    ]
                ),
                CarouselColumn(
                    title='飲食搜索',
                    text='請選擇分類',
                    actions=[
                        MessageAction(label='維生素', text='維生素'),
                        MessageAction(label='礦物質', text='礦物質'),
                        MessageAction(label='其他', text='其他')
                    ]
                )
            ]
            carousel_template = CarouselTemplate(columns=carousel_columns)
            template_message = TemplateMessage(
                alt_text='Carousel alt text',
                template=carousel_template
            )
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[template_message]
                )
            )

        elif text == '醣類':
            sugar_items = random.sample(cleaned_categorized_foods['醣類'], k=5)
            image_carousel_columns = []
            for item in sugar_items:
                image_carousel_columns.append(
                    ImageCarouselColumn(
                        image_url=item['image'],
                        action=URIAction(
                            label=item['name'],
                            uri='https://www.7-11.com.tw/freshfoods/hot.aspx'
                        )
                    )
                )
            image_carousel_template = ImageCarouselTemplate(columns=image_carousel_columns)
            template_message = TemplateMessage(
                alt_text='醣類',
                template=image_carousel_template
            )
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[template_message]
                )
            )

        elif text == '脂質':
            fat_items = random.sample(cleaned_categorized_foods['脂質'], k=5)
            image_carousel_columns = []
            for item in fat_items:
                image_carousel_columns.append(
                    ImageCarouselColumn(
                        image_url=item['image'],
                        action=URIAction(
                            label=item['name'],
                            uri='https://www.7-11.com.tw/freshfoods/19_star/index.aspx'
                        )
                    )
                )
            image_carousel_template = ImageCarouselTemplate(columns=image_carousel_columns)
            template_message = TemplateMessage(
                alt_text='脂質',
                template=image_carousel_template
            )
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[template_message]
                )
            )

        elif text == '蛋白質':
            protein_items = random.sample(cleaned_categorized_foods['蛋白質'], k=5)
            image_carousel_columns = []
            for item in protein_items:
                image_carousel_columns.append(
                    ImageCarouselColumn(
                        image_url=item['image'],
                        action=URIAction(
                            label=item['name'],
                            uri='https://www.7-11.com.tw/freshfoods/3_Cuisine/index.aspx'
                        )
                    )
                )
            image_carousel_template = ImageCarouselTemplate(columns=image_carousel_columns)
            template_message = TemplateMessage(
                alt_text='蛋白質',
                template=image_carousel_template
            )
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[template_message]
                )
            )

        elif text == '維生素':
            vitamin_items =  random.sample(cleaned_categorized_foods['維生素'], k=5)
            image_carousel_columns = []
            for item in vitamin_items:
                image_carousel_columns.append(
                    ImageCarouselColumn(
                        image_url=item['image'],
                        action=URIAction(
                            label=item['name'],
                            uri='https://www.7-11.com.tw/freshfoods/2_Light/index.aspx'
                        )
                    )
                )
            image_carousel_template = ImageCarouselTemplate(columns=image_carousel_columns)
            template_message = TemplateMessage(
                alt_text='維生素',
                template=image_carousel_template
            )
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[template_message]
                )
            )
            
        elif text == '礦物質':
            mineral_items = random.sample(cleaned_categorized_foods['礦物質'], k=5)
            image_carousel_columns = []
            for item in mineral_items:
                image_carousel_columns.append(
                    ImageCarouselColumn(
                        image_url=item['image'],
                        action=URIAction(
                            label=item['name'],
                            uri='https://www.7-11.com.tw/freshfoods/2_Light/index.aspx'
                        )
                    )
                )
            image_carousel_template = ImageCarouselTemplate(columns=image_carousel_columns)
            template_message = TemplateMessage(
                alt_text='礦物質',
                template=image_carousel_template
            )
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[template_message]
                )
            )

        elif text == '其他':
            other_items = random.sample(cleaned_categorized_foods['其他'], k=5)
            image_carousel_columns = []
            for item in other_items:
                image_carousel_columns.append(
                    ImageCarouselColumn(
                        image_url=item['image'],
                        action=URIAction(
                            label=item['name'],
                            uri='https://www.7-11.com.tw/freshfoods/4_Snacks/index.aspx'
                        )
                    )
                )
            image_carousel_template = ImageCarouselTemplate(columns=image_carousel_columns)
            template_message = TemplateMessage(
                alt_text='其他',
                template=image_carousel_template
            )
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[template_message]
                )
            )

        else:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=event.message.text), TextMessage(text=event.message.text)]
                )
            )

if __name__ == "__main__":
    app.run(port=port)

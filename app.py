from flask import Flask, request, jsonify, render_template, make_response, Response
import csv
import io
import os
from playwright.sync_api import sync_playwright
from jsonpath_ng import parse
from pymongo import MongoClient
from dotenv import load_dotenv
import logging
from urllib.parse import quote
from flask_socketio import SocketIO


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)

# MongoDB Connection Setup

# mongo_con = 'mongodb+srv://akrishnapbhat:shoor100@cluster0.avjq4vu.mongodb.net/'
# client = MongoClient(mongo_con)
# db = client['sample_mflix']
# collection = db['Seeding_database']

# Initialize MongoDB collection


# Define the function to extract and update CSV data
def extract_and_update_csv(url, media_type, total_limit):
    # Initialize a set to collect all media URLs
    collected_media_urls = set()
    # Initialize a counter for the total number of URLs collected
    total_count = 0

    # Define JSON path expressions for image and video URLs
    media_url_expr = parse('$..media_url_https')
    json_path_expr = parse('$..variants')

    # Use Playwright browser automation to scrape the URL
    with sync_playwright() as p:
        # Specify the user data path
        # user_data_path = '/Users/amruthakrishna/documents/firefox/AK/Default'  # Update this path as needed
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context()
        page = context.new_page()

        # Define the response handler function
        def handle_response(response):
            nonlocal total_count
            try:
                if response.status == 200 and "SearchTimeline" in response.url:
                    data = response.json()
                    # Extract media URLs (both image and video)
                    if media_type in ['image', 'both']:
                        extracted_media_urls = [match.value for match in media_url_expr.find(data)]
                        extracted_media_urls = [url for url in extracted_media_urls if 'ext_tw_video_thumb' not in url and 'amplify_video_thumb' not in url and 'tweet_video_thumb' not in url]

                        # Update the set and counters
                        for media_url in extracted_media_urls:
                            if media_url not in collected_media_urls and total_count < total_limit:
                                collected_media_urls.add(media_url)
                                total_count += 1

                    # Extract video variants
                    if media_type in ['video', 'both']:
                        extracted_variants = [match.value for match in json_path_expr.find(data)]
                        for variants_list in extracted_variants:
                            if len(variants_list) >= 3:
                                third_variant = variants_list[2]
                                if 'url' in third_variant:
                                    third_url = third_variant['url']
                                    if 'amplify_video' not in third_url:
                                        if third_url not in collected_media_urls and total_count < total_limit:
                                            collected_media_urls.add(third_url)
                                            total_count += 1
                                        
            except Exception as e:
                print(f"Error processing response: {str(e)}")

        # Set up the response handler
        page.on("response", handle_response)

        # Navigate to the provided URL
        page.goto(url)

        # Scroll the page and wait for new content to load
        while total_count < total_limit:
            # Scroll to the bottom of the page
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            print("Link Fetched:",total_count)
            page.wait_for_timeout(5000)
            # Break the loop if the total limit is reached
            if total_count >= total_limit:
                break

        # Close the page and context
        page.close()
        context.close()

    # Return the collected media URLs as a list and the total count
    return list(collected_media_urls), total_count

# Serve the HTML file
@app.route('/')
def index():
    return render_template('index.html')

# Route to handle form submissions and extract media links
@app.route('/get_shorts_links', methods=['POST'])
def get_shorts_links():
    # Get form data from the request
    url = request.form.get('url')
    media_type = request.form.get('media_type')
    limit = int(request.form.get('total_limit'))

    # Call the extract_and_update_csv function and get the results and the total count
    results, total_count = extract_and_update_csv(url, media_type, limit)

    # Return the results and total count as JSON
    return jsonify({
        'shorts_links': results,
        'total_count': total_count
    })

# Route to handle CSV download requests
@app.route('/download_csv', methods=['POST'])
def download_csv():
    # Get the data from the request
    data = request.get_json().get('data')

    # Create a CSV file in memory
    csv_output = io.StringIO()
    writer = csv.DictWriter(csv_output, fieldnames=['link'])
    writer.writeheader()
    writer.writerows({'link': link} for link in data)

    # Move the file pointer to the beginning
    csv_output.seek(0)

    # Create a response object for the CSV file
    response = make_response(csv_output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = 'attachment; filename=output.csv'

    return response

@app.route('/upload_to_mongo', methods=['POST'])
def upload_to_mongo():
    try:
        data = request.get_json()  # Get JSON data from the request
        # print("JSON received by the backend:", data)  # Print the JSON received by the backend
        
        if isinstance(data, list) and data:
            collection.insert_many(data)
            print("File Uploaded to Mongo Successfully!")
            return jsonify({"message": "File Uploaded to Mongo Successfully!"}), 200
        else:
            print("JSON data is empty or not in the expected format.")
            return jsonify({"error": "JSON data is empty or not in the expected format."}), 400
    except FileNotFoundError:
        print(f"File '{data}' not found.")
        return jsonify({"error": f"File '{data}' not found."}), 404
    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({"error": f"An error occurred: {e}"}), 500

if __name__ == '__main__':
    socketio.run(app)

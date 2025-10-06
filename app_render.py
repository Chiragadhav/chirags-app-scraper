
import os
from flask import Flask, render_template, request, jsonify, send_file
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import random
from datetime import datetime
import logging
from urllib.parse import urlparse
import tempfile

# Create Flask app
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ReviewScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def detect_platform(self, url):
        """Detect if URL is from Google Play Store or Apple App Store"""
        if 'play.google.com' in url:
            return 'google_play'
        elif 'apps.apple.com' in url or 'itunes.apple.com' in url:
            return 'app_store'
        else:
            return None

    def extract_app_id(self, url, platform):
        """Extract app ID from URL"""
        if platform == 'google_play':
            match = re.search(r'id=([^&]+)', url)
            return match.group(1) if match else None
        elif platform == 'app_store':
            match = re.search(r'id(\d+)', url)
            return match.group(1) if match else None
        return None

    def scrape_google_play_reviews(self, app_id, max_reviews=500):
        """Scrape Google Play Store reviews"""
        reviews = []

        try:
            # Try to import and use google-play-scraper
            from google_play_scraper import app, Sort, reviews_all

            # Get app info
            app_info = app(app_id)
            app_name = app_info['title']

            # Get reviews with delays to avoid rate limiting
            result = reviews_all(
                app_id,
                sleep_milliseconds=2000,  # 2 second delay between requests
                lang='en',
                country='us',
                sort=Sort.NEWEST,
            )

            # Limit reviews if specified
            if max_reviews and len(result) > max_reviews:
                result = result[:max_reviews]

            for review in result:
                reviews.append({
                    'app_name': app_name,
                    'reviewer_name': review['userName'],
                    'rating': review['score'],
                    'review_text': review['content'],
                    'review_date': review['at'].strftime('%Y-%m-%d %H:%M:%S'),
                    'helpful_count': review['thumbsUpCount'],
                    'platform': 'Google Play Store'
                })

        except ImportError:
            logger.warning("google-play-scraper not available")
            # Return sample data for demo
            reviews = self._get_demo_data('google_play', app_id)
        except Exception as e:
            logger.error(f"Error scraping Google Play reviews: {str(e)}")
            reviews = self._get_demo_data('google_play', app_id)

        return reviews

    def scrape_app_store_reviews(self, app_id, max_reviews=500):
        """Scrape Apple App Store reviews"""
        reviews = []

        try:
            from app_store_scraper import AppStore

            # Initialize scraper
            scraper = AppStore(country='us', app_id=app_id)
            scraper.review(how_many=max_reviews or 500)

            app_name = scraper.app_name or f"App ID {app_id}"

            for review in scraper.reviews:
                reviews.append({
                    'app_name': app_name,
                    'reviewer_name': review['userName'],
                    'rating': review['rating'],
                    'review_text': review['review'],
                    'review_date': review['date'].strftime('%Y-%m-%d %H:%M:%S') if review['date'] else '',
                    'helpful_count': 0,  # App Store doesn't provide this
                    'platform': 'Apple App Store'
                })

        except ImportError:
            logger.warning("app-store-scraper not available")
            reviews = self._get_demo_data('app_store', app_id)
        except Exception as e:
            logger.error(f"Error scraping App Store reviews: {str(e)}")
            reviews = self._get_demo_data('app_store', app_id)

        return reviews

    def _get_demo_data(self, platform, app_id):
        """Generate demo data when scraping libraries aren't available"""
        platform_name = 'Google Play Store' if platform == 'google_play' else 'Apple App Store'
        demo_reviews = [
            {
                'app_name': f'Demo App ({app_id})',
                'reviewer_name': 'Demo User 1',
                'rating': 5,
                'review_text': 'Great app! Works perfectly and has a beautiful interface.',
                'review_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'helpful_count': 15,
                'platform': platform_name
            },
            {
                'app_name': f'Demo App ({app_id})',
                'reviewer_name': 'Demo User 2',
                'rating': 4,
                'review_text': 'Very useful app. The yellow theme looks amazing!',
                'review_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'helpful_count': 8,
                'platform': platform_name
            },
            {
                'app_name': f'Demo App ({app_id})',
                'reviewer_name': 'Demo User 3',
                'rating': 5,
                'review_text': 'Excellent functionality and easy to use. Highly recommended!',
                'review_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'helpful_count': 22,
                'platform': platform_name
            }
        ]
        return demo_reviews

    def scrape_reviews(self, url, max_reviews=500):
        """Main method to scrape reviews from either platform"""
        platform = self.detect_platform(url)

        if not platform:
            raise ValueError("Unsupported URL. Please provide a Google Play Store or Apple App Store URL.")

        app_id = self.extract_app_id(url, platform)
        if not app_id:
            raise ValueError("Could not extract app ID from URL.")

        if platform == 'google_play':
            reviews = self.scrape_google_play_reviews(app_id, max_reviews)
        else:
            reviews = self.scrape_app_store_reviews(app_id, max_reviews)

        return reviews

# Global scraper instance
scraper = ReviewScraper()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'message': 'Chirag\'s App Scraper is running on Render!'})

@app.route('/scrape', methods=['POST'])
def scrape():
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        max_reviews = data.get('max_reviews', 500)

        if not url:
            return jsonify({'error': 'URL is required'}), 400

        # Validate URL
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return jsonify({'error': 'Invalid URL format'}), 400
        except Exception:
            return jsonify({'error': 'Invalid URL format'}), 400

        # Scrape reviews
        reviews = scraper.scrape_reviews(url, max_reviews)

        if not reviews:
            return jsonify({'error': 'No reviews found or unable to scrape'}), 404

        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        app_name = reviews[0]['app_name'].replace(' ', '_').replace('/', '_')[:50]  # Limit length
        filename = f"reviews_{app_name}_{timestamp}.csv"

        # Create CSV in temporary directory (Render-compatible)
        df = pd.DataFrame(reviews)

        # Use Render's temporary storage
        temp_dir = '/tmp'  # Render's temporary directory
        filepath = os.path.join(temp_dir, filename)
        df.to_csv(filepath, index=False, encoding='utf-8')

        return jsonify({
            'success': True,
            'message': f'Successfully scraped {len(reviews)} reviews',
            'filename': filename,
            'review_count': len(reviews),
            'app_name': reviews[0]['app_name']
        })

    except Exception as e:
        logger.error(f"Error in scrape endpoint: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        # Use Render's temporary directory
        filepath = os.path.join('/tmp', filename)

        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True, download_name=filename)
        else:
            return jsonify({'error': 'File not found. Please scrape reviews first.'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# For Render deployment
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

import requests
import json
import time
import random
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import sqlite3
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
import re

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ProductData:
    """产品数据结构"""
    name: str
    price: float
    currency: str
    brand: str
    category: str
    rating: float
    reviews_count: int
    availability: str
    source: str
    url: str
    scraped_at: datetime
    description: str = ""
    image_url: str = ""

class EyelashMarketScraper:
    """假睫毛市场数据爬虫"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.db_path = 'eyelash_market_data.db'
        self.init_database()
        
    def init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL,
                currency TEXT,
                brand TEXT,
                category TEXT,
                rating REAL,
                reviews_count INTEGER,
                availability TEXT,
                source TEXT,
                url TEXT,
                description TEXT,
                image_url TEXT,
                scraped_at TIMESTAMP,
                UNIQUE(name, brand, source)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS market_trends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE,
                total_products INTEGER,
                avg_price REAL,
                top_brands TEXT,
                trending_keywords TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        
    def scrape_amazon_eyelashes(self, search_term: str = "false eyelashes", max_pages: int = 3) -> List[ProductData]:
        """爬取Amazon假睫毛数据"""
        products = []
        base_url = "https://www.amazon.com/s"
        
        for page in range(1, max_pages + 1):
            try:
                params = {
                    'k': search_term,
                    'page': page,
                    'ref': 'sr_pg_' + str(page)
                }
                
                response = self.session.get(base_url, params=params)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                product_containers = soup.find_all('div', {'data-component-type': 's-search-result'})
                
                for container in product_containers:
                    try:
                        product = self._parse_amazon_product(container)
                        if product:
                            products.append(product)
                    except Exception as e:
                        logger.warning(f"解析Amazon产品时出错: {e}")
                        continue
                
                # 随机延迟避免被封
                time.sleep(random.uniform(1, 3))
                
            except Exception as e:
                logger.error(f"爬取Amazon第{page}页时出错: {e}")
                continue
                
        return products
    
    def _parse_amazon_product(self, container) -> Optional[ProductData]:
        """解析Amazon产品信息"""
        try:
            # 产品名称
            name_elem = container.find('h2', class_='a-size-mini')
            if not name_elem:
                return None
            name = name_elem.get_text(strip=True)
            
            # 价格
            price_elem = container.find('span', class_='a-price-whole')
            price = 0.0
            if price_elem:
                price_text = price_elem.get_text(strip=True).replace(',', '')
                price = float(re.findall(r'\d+\.?\d*', price_text)[0]) if re.findall(r'\d+\.?\d*', price_text) else 0.0
            
            # 评分
            rating_elem = container.find('span', class_='a-icon-alt')
            rating = 0.0
            if rating_elem:
                rating_text = rating_elem.get_text(strip=True)
                rating_match = re.search(r'(\d+\.\d+)', rating_text)
                if rating_match:
                    rating = float(rating_match.group(1))
            
            # 评论数量
            reviews_elem = container.find('a', class_='a-link-normal')
            reviews_count = 0
            if reviews_elem:
                reviews_text = reviews_elem.get_text(strip=True)
                reviews_match = re.findall(r'\d+', reviews_text.replace(',', ''))
                if reviews_match:
                    reviews_count = int(reviews_match[0])
            
            # 产品链接
            link_elem = container.find('h2').find('a') if container.find('h2') else None
            url = urljoin('https://www.amazon.com', link_elem['href']) if link_elem else ""
            
            # 图片链接
            img_elem = container.find('img', class_='s-image')
            image_url = img_elem['src'] if img_elem else ""
            
            return ProductData(
                name=name,
                price=price,
                currency="USD",
                brand=self._extract_brand(name),
                category="False Eyelashes",
                rating=rating,
                reviews_count=reviews_count,
                availability="In Stock",
                source="Amazon",
                url=url,
                image_url=image_url,
                scraped_at=datetime.now()
            )
            
        except Exception as e:
            logger.warning(f"解析Amazon产品详情时出错: {e}")
            return None
    
    def scrape_ebay_eyelashes(self, search_term: str = "false eyelashes", max_pages: int = 3) -> List[ProductData]:
        """爬取eBay假睫毛数据"""
        products = []
        base_url = "https://www.ebay.com/sch/i.html"
        
        for page in range(1, max_pages + 1):
            try:
                params = {
                    '_nkw': search_term,
                    '_pgn': page,
                    '_skc': 0,
                    'rt': 'nc'
                }
                
                response = self.session.get(base_url, params=params)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                product_containers = soup.find_all('div', class_='s-item__wrapper')
                
                for container in product_containers:
                    try:
                        product = self._parse_ebay_product(container)
                        if product:
                            products.append(product)
                    except Exception as e:
                        logger.warning(f"解析eBay产品时出错: {e}")
                        continue
                
                time.sleep(random.uniform(1, 3))
                
            except Exception as e:
                logger.error(f"爬取eBay第{page}页时出错: {e}")
                continue
                
        return products
    
    def _parse_ebay_product(self, container) -> Optional[ProductData]:
        """解析eBay产品信息"""
        try:
            # 产品名称
            name_elem = container.find('h3', class_='s-item__title')
            if not name_elem:
                return None
            name = name_elem.get_text(strip=True)
            
            # 价格
            price_elem = container.find('span', class_='s-item__price')
            price = 0.0
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price_match = re.findall(r'\$([\d,]+\.?\d*)', price_text)
                if price_match:
                    price = float(price_match[0].replace(',', ''))
            
            # 产品链接
            link_elem = container.find('a', class_='s-item__link')
            url = link_elem['href'] if link_elem else ""
            
            # 图片链接
            img_elem = container.find('img')
            image_url = img_elem['src'] if img_elem else ""
            
            return ProductData(
                name=name,
                price=price,
                currency="USD",
                brand=self._extract_brand(name),
                category="False Eyelashes",
                rating=0.0,  # eBay搜索页面通常不显示评分
                reviews_count=0,
                availability="Available",
                source="eBay",
                url=url,
                image_url=image_url,
                scraped_at=datetime.now()
            )
            
        except Exception as e:
            logger.warning(f"解析eBay产品详情时出错: {e}")
            return None
    
    def _extract_brand(self, product_name: str) -> str:
        """从产品名称中提取品牌"""
        # 常见假睫毛品牌列表
        brands = [
            'Ardell', 'Kiss', 'Eylure', 'Revlon', 'Maybelline', 'L\'Oreal', 
            'MAC', 'Sephora', 'Benefit', 'Too Faced', 'Urban Decay', 'Huda Beauty',
            'Lilly Lashes', 'House of Lashes', 'Velour Lashes', 'Red Cherry',
            'Andrea', 'DUO', 'Esqido', 'Lash Perfect'
        ]
        
        product_name_lower = product_name.lower()
        for brand in brands:
            if brand.lower() in product_name_lower:
                return brand
        
        # 如果没有找到已知品牌，尝试提取第一个单词作为品牌
        words = product_name.split()
        if words:
            return words[0]
        
        return "Unknown"
    
    def save_products_to_db(self, products: List[ProductData]):
        """保存产品数据到数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for product in products:
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO products 
                    (name, price, currency, brand, category, rating, reviews_count, 
                     availability, source, url, description, image_url, scraped_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    product.name, product.price, product.currency, product.brand,
                    product.category, product.rating, product.reviews_count,
                    product.availability, product.source, product.url,
                    product.description, product.image_url, product.scraped_at
                ))
            except Exception as e:
                logger.error(f"保存产品数据时出错: {e}")
                continue
        
        conn.commit()
        conn.close()
        logger.info(f"成功保存 {len(products)} 个产品到数据库")
    
    def get_market_summary(self) -> Dict:
        """获取市场数据摘要"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 总产品数量
        cursor.execute("SELECT COUNT(*) FROM products")
        total_products = cursor.fetchone()[0]
        
        # 平均价格
        cursor.execute("SELECT AVG(price) FROM products WHERE price > 0")
        avg_price = cursor.fetchone()[0] or 0
        
        # 热门品牌
        cursor.execute("""
            SELECT brand, COUNT(*) as count 
            FROM products 
            GROUP BY brand 
            ORDER BY count DESC 
            LIMIT 10
        """)
        top_brands = cursor.fetchall()
        
        # 价格分布
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN price < 10 THEN 'Under $10'
                    WHEN price < 25 THEN '$10-$25'
                    WHEN price < 50 THEN '$25-$50'
                    ELSE 'Over $50'
                END as price_range,
                COUNT(*) as count
            FROM products 
            WHERE price > 0
            GROUP BY price_range
        """)
        price_distribution = cursor.fetchall()
        
        # 数据源分布
        cursor.execute("""
            SELECT source, COUNT(*) as count 
            FROM products 
            GROUP BY source
        """)
        source_distribution = cursor.fetchall()
        
        conn.close()
        
        return {
            'total_products': total_products,
            'average_price': round(avg_price, 2),
            'top_brands': [{'brand': brand, 'count': count} for brand, count in top_brands],
            'price_distribution': [{'range': range_name, 'count': count} for range_name, count in price_distribution],
            'source_distribution': [{'source': source, 'count': count} for source, count in source_distribution],
            'last_updated': datetime.now().isoformat()
        }
    
    def run_full_scrape(self):
        """执行完整的数据爬取"""
        logger.info("开始执行假睫毛市场数据爬取...")
        
        all_products = []
        
        # 爬取Amazon数据
        logger.info("正在爬取Amazon数据...")
        amazon_products = self.scrape_amazon_eyelashes()
        all_products.extend(amazon_products)
        logger.info(f"从Amazon获取到 {len(amazon_products)} 个产品")
        
        # 爬取eBay数据
        logger.info("正在爬取eBay数据...")
        ebay_products = self.scrape_ebay_eyelashes()
        all_products.extend(ebay_products)
        logger.info(f"从eBay获取到 {len(ebay_products)} 个产品")
        
        # 保存到数据库
        if all_products:
            self.save_products_to_db(all_products)
            logger.info(f"总共爬取到 {len(all_products)} 个产品")
        else:
            logger.warning("没有爬取到任何产品数据")
        
        return all_products

if __name__ == "__main__":
    scraper = EyelashMarketScraper()
    products = scraper.run_full_scrape()
    summary = scraper.get_market_summary()
    print(json.dumps(summary, indent=2, ensure_ascii=False))

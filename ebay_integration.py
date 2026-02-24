"""
eBay API Integration for Sports Card Value Estimator
Handles OAuth, sold listings search, and data parsing.
Sandbox + Production support.

Author: HutchGroup LLC
"""

import base64
import time
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import json

try:
    import requests
except ImportError:
    requests = None  # Graceful fallback for environments without requests

from card_value_engine import MarketDataPoint, CardAttributes, CardCondition


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class EbayConfig:
    """eBay API configuration."""
    client_id: str
    client_secret: str = ""   # Optional — Finding API works with App ID only
    sandbox: bool = True
    
    @property
    def auth_url(self) -> str:
        if self.sandbox:
            return "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
        return "https://api.ebay.com/identity/v1/oauth2/token"
    
    @property
    def browse_url(self) -> str:
        if self.sandbox:
            return "https://api.sandbox.ebay.com/buy/browse/v1"
        return "https://api.ebay.com/buy/browse/v1"
    
    @property
    def finding_url(self) -> str:
        if self.sandbox:
            return "https://svcs.sandbox.ebay.com/services/search/FindingService/v1"
        return "https://svcs.ebay.com/services/search/FindingService/v1"
    
    @property
    def scope(self) -> str:
        return "https://api.ebay.com/oauth/api_scope"


# ============================================================================
# TOKEN MANAGER — handles OAuth with auto-refresh
# ============================================================================

class TokenManager:
    """
    Manages eBay OAuth tokens. Automatically refreshes before expiry.
    Uses client credentials flow (no user login needed for sold data).
    """
    
    def __init__(self, config: EbayConfig):
        self.config = config
        self._token: Optional[str] = None
        self._expires_at: float = 0.0
    
    @property
    def token(self) -> str:
        """Get a valid access token, refreshing if needed."""
        if self._token and time.time() < (self._expires_at - 60):
            return self._token
        return self._refresh()
    
    def _refresh(self) -> str:
        """Mint a new application access token."""
        if requests is None:
            raise RuntimeError("requests library required for eBay API")
        
        # Base64 encode credentials
        credentials = f"{self.config.client_id}:{self.config.client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded}",
        }
        
        body = {
            "grant_type": "client_credentials",
            "scope": self.config.scope,
        }
        
        response = requests.post(
            self.config.auth_url,
            headers=headers,
            data=body,
            timeout=10,
        )
        
        if response.status_code != 200:
            error = response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
            raise RuntimeError(f"eBay OAuth failed ({response.status_code}): {error}")
        
        data = response.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + data.get("expires_in", 7200)
        
        return self._token


# ============================================================================
# RATE LIMITER — simple sliding window
# ============================================================================

class RateLimiter:
    """
    Simple rate limiter: max N calls per window.
    eBay allows 5,000 calls/day for Browse API.
    """
    
    def __init__(self, max_calls: int = 5000, window_seconds: int = 86400):
        self.max_calls = max_calls
        self.window = window_seconds
        self._timestamps: List[float] = []
    
    def acquire(self) -> bool:
        """Try to acquire a rate limit slot. Returns True if allowed."""
        now = time.time()
        cutoff = now - self.window
        self._timestamps = [t for t in self._timestamps if t > cutoff]
        
        if len(self._timestamps) >= self.max_calls:
            return False
        
        self._timestamps.append(now)
        return True
    
    @property
    def remaining(self) -> int:
        now = time.time()
        cutoff = now - self.window
        active = sum(1 for t in self._timestamps if t > cutoff)
        return max(0, self.max_calls - active)


# ============================================================================
# eBay DATA FETCHER
# ============================================================================

class EbayMarketFetcher:
    """
    Fetches real sold listing data from eBay.
    
    Uses Browse API (search with filter on sold items) or
    Finding API (findCompletedItems) depending on availability.
    """
    
    def __init__(self, config: EbayConfig):
        self.config = config
        self.tokens = TokenManager(config)
        self.limiter = RateLimiter(max_calls=4500)  # Leave buffer
        self._cache: Dict[str, tuple] = {}  # key -> (timestamp, data)
        self.cache_ttl = 3600  # 1 hour cache
    
    def fetch_sold_listings(self, card: CardAttributes, 
                            limit: int = 10) -> List[MarketDataPoint]:
        """
        Fetch sold listings for a card from eBay.
        Returns MarketDataPoint objects ready for the value engine.
        """
        if requests is None:
            return []
        
        # Check cache
        cache_key = self._cache_key(card)
        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                return cached_data
        
        # Check rate limit
        if not self.limiter.acquire():
            print("eBay rate limit reached — falling back to cached/mock data")
            return []
        
        try:
            # Build search query
            query = self._build_query(card)
            
            # Browse API needs OAuth (client_secret). Finding API only needs App ID.
            # If no secret, skip straight to Finding API.
            results = []
            if self.config.client_secret:
                results = self._search_browse_api(query, limit)
            
            if not results:
                results = self._search_finding_api(query, limit)
            
            # Parse into MarketDataPoints
            data_points = self._parse_results(results, card)
            
            # Cache results
            self._cache[cache_key] = (time.time(), data_points)
            
            return data_points
            
        except Exception as e:
            print(f"eBay API error: {e}")
            return []
    
    def _build_query(self, card: CardAttributes) -> str:
        """Build eBay search query from card attributes."""
        parts = [card.player, str(card.year), card.set_name]
        
        if card.parallel:
            parts.append(card.parallel)
        if card.card_number:
            parts.append(f"#{card.card_number}")
        if card.rookie:
            parts.append("RC")
        if card.autograph:
            parts.append("auto")
        if card.serial_number:
            # Add print run info
            match = re.search(r'/(\d+)', card.serial_number)
            if match:
                parts.append(f"/{match.group(1)}")
        
        return " ".join(parts)
    
    def _search_browse_api(self, query: str, limit: int) -> List[Dict]:
        """Search using eBay Browse API."""
        try:
            token = self.tokens.token
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            }
            
            params = {
                "q": query,
                "category_ids": "261328",  # Sports Trading Cards
                "filter": "buyingOptions:{FIXED_PRICE|AUCTION},conditionIds:{1000|1500|2000|2500|3000}",
                "sort": "-price",
                "limit": min(limit, 50),
            }
            
            url = f"{self.config.browse_url}/item_summary/search"
            response = requests.get(url, headers=headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                return data.get("itemSummaries", [])
            
            return []
            
        except Exception as e:
            print(f"Browse API error: {e}")
            return []
    
    def _search_finding_api(self, query: str, limit: int) -> List[Dict]:
        """Fallback: search using eBay Finding API (findCompletedItems)."""
        try:
            headers = {
                "X-EBAY-SOA-SECURITY-APPNAME": self.config.client_id,
                "X-EBAY-SOA-OPERATION-NAME": "findCompletedItems",
                "X-EBAY-SOA-SERVICE-VERSION": "1.13.0",
                "X-EBAY-SOA-RESPONSE-DATA-FORMAT": "JSON",
            }
            
            params = {
                "keywords": query,
                "categoryId": "261328",
                "itemFilter(0).name": "SoldItemsOnly",
                "itemFilter(0).value": "true",
                "sortOrder": "EndTimeSoonest",
                "paginationInput.entriesPerPage": min(limit, 100),
            }
            
            response = requests.get(
                self.config.finding_url, 
                headers=headers, 
                params=params, 
                timeout=15,
            )
            
            if response.status_code == 200:
                data = response.json()
                search_result = (
                    data.get("findCompletedItemsResponse", [{}])[0]
                    .get("searchResult", [{}])[0]
                )
                return search_result.get("item", [])
            
            return []
            
        except Exception as e:
            print(f"Finding API error: {e}")
            return []
    
    def _parse_results(self, results: List[Dict], 
                       card: CardAttributes) -> List[MarketDataPoint]:
        """Parse eBay API results into MarketDataPoint objects."""
        points = []
        
        for item in results:
            try:
                # Handle both Browse API and Finding API response formats
                price = self._extract_price(item)
                date = self._extract_date(item)
                url = self._extract_url(item)
                
                if price and price > 0:
                    points.append(MarketDataPoint(
                        source="ebay_sold",
                        value=round(price, 2),
                        date=date or datetime.now(),
                        sample_size=1,
                        condition=card.condition,
                        url=url,
                        notes="eBay sold listing",
                    ))
            except (KeyError, ValueError, TypeError):
                continue
        
        return points
    
    def _extract_price(self, item: Dict) -> Optional[float]:
        """Extract price from either API format."""
        # Browse API format
        if "price" in item:
            return float(item["price"].get("value", 0))
        
        # Finding API format
        selling = item.get("sellingStatus", [{}])
        if isinstance(selling, list) and selling:
            current_price = selling[0].get("currentPrice", [{}])
            if isinstance(current_price, list) and current_price:
                return float(current_price[0].get("__value__", 0))
        
        return None
    
    def _extract_date(self, item: Dict) -> Optional[datetime]:
        """Extract sale date from either API format."""
        # Browse API
        if "itemEndDate" in item:
            try:
                return datetime.fromisoformat(item["itemEndDate"].replace("Z", "+00:00"))
            except ValueError:
                pass
        
        # Finding API
        end_time = item.get("listingInfo", [{}])
        if isinstance(end_time, list) and end_time:
            time_str = end_time[0].get("endTime", [None])
            if isinstance(time_str, list) and time_str and time_str[0]:
                try:
                    return datetime.fromisoformat(time_str[0].replace("Z", "+00:00"))
                except ValueError:
                    pass
        
        return None
    
    def _extract_url(self, item: Dict) -> Optional[str]:
        """Extract item URL from either API format."""
        return item.get("itemWebUrl") or item.get("viewItemURL", [None])
    
    def _cache_key(self, card: CardAttributes) -> str:
        return f"{card.player}|{card.year}|{card.set_name}|{card.parallel or ''}|{card.serial_number or ''}"


# ============================================================================
# INTEGRATED MARKET DATA FETCHER (replaces empty placeholder)
# ============================================================================

class MarketDataFetcher:
    """
    Unified fetcher that pulls from eBay (real) + other sources (mock for now).
    Drop-in replacement for the placeholder in v2.
    """
    
    def __init__(self, ebay_config: Optional[EbayConfig] = None):
        self.ebay: Optional[EbayMarketFetcher] = None
        if ebay_config:
            self.ebay = EbayMarketFetcher(ebay_config)
    
    def fetch_all(self, card: CardAttributes) -> List[MarketDataPoint]:
        """
        Fetch from all available sources.
        eBay = real data. Others = mock until we integrate them.
        """
        points = []
        
        # Real eBay data
        if self.ebay:
            ebay_points = self.ebay.fetch_sold_listings(card, limit=10)
            points.extend(ebay_points)
        
        # TODO: Real 130point integration
        # TODO: Real PSA APR integration
        # TODO: Real Beckett integration
        
        # If we got no real data, fall back to mock
        if not points:
            from card_value_engine import MockDataFactory
            points = MockDataFactory.generate(card)
        
        return points


# ============================================================================
# CONVENIENCE: Create fetcher from environment or direct keys
# ============================================================================

def create_ebay_fetcher(client_id: str, client_secret: str, 
                        sandbox: bool = True) -> MarketDataFetcher:
    """Quick setup for eBay integration (Browse API + Finding API)."""
    config = EbayConfig(
        client_id=client_id,
        client_secret=client_secret,
        sandbox=sandbox,
    )
    return MarketDataFetcher(ebay_config=config)


def create_ebay_fetcher_appid_only(client_id: str,
                                   sandbox: bool = False) -> MarketDataFetcher:
    """Finding API only — no client secret needed. Uses sold comp search."""
    config = EbayConfig(client_id=client_id, sandbox=sandbox)
    return MarketDataFetcher(ebay_config=config)


# ============================================================================
# SMOKE TEST
# ============================================================================

if __name__ == "__main__":
    import os
    
    # Check for keys
    client_id = os.environ.get("EBAY_CLIENT_ID", "")
    client_secret = os.environ.get("EBAY_CLIENT_SECRET", "")
    
    if client_id and client_secret:
        print("eBay API keys found — testing real connection...")
        fetcher = create_ebay_fetcher(client_id, client_secret, sandbox=True)
        
        from card_value_engine import CardAttributes, Sport, CardCondition
        
        test_card = CardAttributes(
            player="Patrick Mahomes",
            year=2017,
            set_name="Prizm",
            card_number="269",
            sport=Sport.FOOTBALL,
            rookie=True,
        )
        
        results = fetcher.fetch_all(test_card)
        print(f"Got {len(results)} data points")
        for r in results[:3]:
            print(f"  {r.source}: ${r.value:.2f} ({r.date.strftime('%Y-%m-%d')})")
    else:
        print("No eBay API keys set. Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET.")
        print("Testing with mock data fallback...")
        
        fetcher = MarketDataFetcher()  # No eBay config = mock only
        
        from card_value_engine import CardAttributes, Sport, MockDataFactory
        
        test_card = CardAttributes(
            player="Patrick Mahomes",
            year=2017,
            set_name="Prizm",
            card_number="269",
            sport=Sport.FOOTBALL,
            rookie=True,
        )
        
        results = fetcher.fetch_all(test_card)
        print(f"Mock data: {len(results)} data points")
        for r in results[:3]:
            print(f"  {r.source}: ${r.value:.2f}")

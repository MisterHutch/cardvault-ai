"""
Sports Card Identifier - Enhanced Version
Uses Claude Vision API with improved prompts for parallel/SSP detection.

Author: HutchGroup LLC
"""

import anthropic
import base64
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import json
import re


@dataclass
class CardIdentification:
    """Represents the identification results for a single card."""
    # Core identification
    player_name: str = "Unknown"
    team: str = "Unknown"
    year: str = "Unknown"
    sport: str = "Unknown"
    position: str = "Unknown"
    
    # Card details
    brand: str = "Unknown"  # Panini, Topps, etc.
    set_name: str = "Unknown"  # Prizm, Mosaic, Select, Phoenix, etc.
    subset: str = ""  # Insert name if applicable
    card_number: str = "Unknown"
    parallel: str = "Base"  # Base, Silver, Gold, Red, etc.
    
    # Special attributes (KEY REQUIREMENTS)
    is_rookie: bool = False
    is_auto: bool = False
    is_patch: bool = False
    is_memorabilia: bool = False
    is_numbered: bool = False
    numbering: str = ""  # e.g., "/99", "/25", "/10"
    is_ssp: bool = False
    ssp_type: str = ""  # Why it's SSP: "Low serial", "Case hit", "1/1", etc.
    
    # Confidence
    confidence: float = 0.0
    identification_notes: str = ""
    
    # Raw data
    raw_response: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_name": self.player_name,
            "team": self.team,
            "year": self.year,
            "sport": self.sport,
            "position": self.position,
            "brand": self.brand,
            "set_name": self.set_name,
            "subset": self.subset,
            "card_number": self.card_number,
            "parallel": self.parallel,
            "is_rookie": self.is_rookie,
            "is_auto": self.is_auto,
            "is_patch": self.is_patch,
            "is_memorabilia": self.is_memorabilia,
            "is_numbered": self.is_numbered,
            "numbering": self.numbering,
            "is_ssp": self.is_ssp,
            "ssp_type": self.ssp_type,
            "confidence": self.confidence,
            "identification_notes": self.identification_notes
        }
    
    def get_special_attributes(self) -> List[str]:
        """Get list of special attributes."""
        attrs = []
        if self.is_rookie:
            attrs.append("RC")
        if self.is_auto:
            attrs.append("AUTO")
        if self.is_patch:
            attrs.append("PATCH")
        elif self.is_memorabilia:
            attrs.append("MEMO")
        if self.is_numbered and self.numbering:
            attrs.append(self.numbering)
        if self.is_ssp:
            attrs.append("SSP")
        return attrs
    
    def summary(self) -> str:
        """Generate a human-readable summary."""
        parts = []
        if self.year and self.year != "Unknown":
            parts.append(self.year)
        if self.brand and self.brand != "Unknown":
            parts.append(self.brand)
        if self.set_name and self.set_name != "Unknown":
            parts.append(self.set_name)
        if self.subset:
            parts.append(self.subset)
        if self.parallel and self.parallel != "Base":
            parts.append(self.parallel)
        if self.player_name and self.player_name != "Unknown":
            parts.append(self.player_name)
        
        attrs = self.get_special_attributes()
        if attrs:
            parts.append(f"({', '.join(attrs)})")
            
        return " ".join(parts) if parts else "Unknown Card"


class CardIdentifier:
    """
    Identifies sports cards using Claude Vision API.
    Enhanced with detailed prompts for parallel and SSP detection.
    """
    
    # Comprehensive identification prompt
    IDENTIFICATION_PROMPT = """You are an expert sports card identifier. Analyze this trading card image and extract all relevant information.

## CRITICAL IDENTIFICATION POINTS:

### 1. PLAYER & TEAM
- Read the player name carefully (usually at bottom or top)
- Identify team from logo, jersey, or text
- Note player position if visible

### 2. CARD SET IDENTIFICATION
Look for these common brands and sets:

**Panini Products:**
- Prizm (signature prismatic refractor pattern)
- Mosaic (mosaic/tile pattern background)
- Select (tiered: Concourse, Premier Level, Club Level)
- Phoenix (flame/fire design elements)
- Prestige (classic design, often with "Prestige" text)
- Donruss/Donruss Optic (rated rookie shield logo)
- Contenders (ticket-style design)
- Score (budget-friendly, "Score" logo)
- Chronicles (multiple brand designs in one product)
- Absolute (jersey swatch windows common)
- National Treasures (ultra-premium)

**Topps Products:**
- Chrome (chromium finish)
- Finest (refractor technology)
- Dynasty (premium with autos/patches)
- Bowman (prospect focused)

### 3. PARALLEL IDENTIFICATION (VERY IMPORTANT)
Common parallel types to identify:

**Prizm Parallels:**
- Base (no special finish)
- Silver Prizm (silver prismatic, most common refractor)
- Red/White/Blue (patriotic shimmer)
- Green, Orange, Purple, Pink, Blue (solid color prizm)
- Gold (/10 typically)
- Black (/1 or /5)
- Neon Green, Neon Orange, Neon Pink
- Mojo (swirl pattern)
- Shimmer
- Snakeskin, Tiger, Camo patterns

**Prestige Parallels:**
- Base
- Xtra Points (colored borders - Red, Blue, Green, Purple, Gold)
- Xtra Points Astral/Galactic (holographic rainbow effect)

**Select Parallels:**
- Base, Silver, Blue, Orange, Green, Gold, Black
- Tie-Dye, Zebra, Disco (special patterns)

**Mosaic Parallels:**
- Base
- Silver, Blue, Green, Orange, Red, Gold
- Reactive (color-shift)
- Genesis (rainbow)

### 4. SPECIAL ATTRIBUTES (CHECK ALL THAT APPLY)

**Rookie Card (RC):**
- Look for "RC" logo/badge
- "Rookie" text
- Rookie card shield/emblem
- First-year player card

**Autograph (AUTO):**
- On-card signature (pen ink visible)
- Sticker autograph
- "Autograph" text on card

**Patch/Memorabilia (PATCH/MEMO):**
- Jersey swatch window
- Multi-color patch piece
- "Player-Worn" or "Game-Used" text
- Fabric/material embedded in card

**Numbered/Serial Numbered:**
- Look for "/XX" numbering (e.g., "25/99", "01/10")
- Usually on front or back of card
- Hand-stamped or printed

**SSP (Short Print/Super Short Print):**
Mark as SSP if ANY of these apply:
- Serial numbered /25 or lower
- Gold parallel
- Black parallel  
- 1/1 cards
- Case hit parallels (Neon, Shimmer, Gold Vinyl)
- Specific known SSP variations

### 5. CARD NUMBER
- Usually on back of card
- Format varies: "123", "#123", "FB-123"

## RESPONSE FORMAT

Respond with ONLY this JSON (no other text):

```json
{
    "player_name": "Full Player Name",
    "team": "Team Name",
    "year": "2023-24 or 2023",
    "sport": "Football|Basketball|Baseball|Hockey|Soccer",
    "position": "QB|RB|WR|TE|etc",
    "brand": "Panini|Topps|etc",
    "set_name": "Prizm|Mosaic|Select|etc",
    "subset": "Insert name if applicable, empty string if base",
    "card_number": "#123 or Unknown",
    "parallel": "Specific parallel name (Base if standard)",
    "is_rookie": true/false,
    "is_auto": true/false,
    "is_patch": true/false,
    "is_memorabilia": true/false,
    "is_numbered": true/false,
    "numbering": "/99 or empty string",
    "is_ssp": true/false,
    "ssp_type": "Reason for SSP classification or empty string",
    "confidence": 0.0-1.0,
    "identification_notes": "Any uncertainty or additional observations"
}
```

## CONFIDENCE SCORING GUIDE:
- 0.95-1.0: All text clearly readable, certain identification
- 0.85-0.94: Most details clear, minor uncertainty
- 0.70-0.84: Some details unclear but reasonable guess
- 0.50-0.69: Significant uncertainty, best guess
- Below 0.50: Cannot reliably identify

Now analyze the card image:"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the identifier.
        
        Args:
            api_key: Anthropic API key. If None, uses ANTHROPIC_API_KEY env var.
        """
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.model = "claude-sonnet-4-20250514"
    
    def _encode_image(self, image_path: str) -> tuple[str, str]:
        """Encode image to base64 and determine media type."""
        path = Path(image_path)
        suffix = path.suffix.lower()
        
        media_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        
        media_type = media_types.get(suffix, 'image/jpeg')
        
        with open(path, 'rb') as f:
            image_data = base64.standard_b64encode(f.read()).decode('utf-8')
        
        return image_data, media_type
    
    def _parse_response(self, raw_text: str) -> Dict[str, Any]:
        """Parse JSON from response, handling various formats."""
        # Try to extract JSON from markdown code block
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', raw_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON object directly
            json_match = re.search(r'\{[^{}]*\}', raw_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = raw_text.strip()
        
        return json.loads(json_str)
    
    def identify_card(self, image_path: str) -> CardIdentification:
        """
        Identify a single card from an image file.
        
        Args:
            image_path: Path to the card image
            
        Returns:
            CardIdentification object with results
        """
        image_data, media_type = self._encode_image(image_path)
        return self.identify_card_from_base64(image_data, media_type)
    
    def identify_card_from_base64(self, image_data: str, media_type: str = "image/jpeg") -> CardIdentification:
        """
        Identify a card from base64-encoded image data.
        
        Args:
            image_data: Base64-encoded image
            media_type: MIME type of the image
            
        Returns:
            CardIdentification object with results
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data
                                }
                            },
                            {
                                "type": "text",
                                "text": self.IDENTIFICATION_PROMPT
                            }
                        ]
                    }
                ]
            )
            
            raw_text = response.content[0].text
            data = self._parse_response(raw_text)
            
            return CardIdentification(
                player_name=data.get("player_name", "Unknown"),
                team=data.get("team", "Unknown"),
                year=data.get("year", "Unknown"),
                sport=data.get("sport", "Unknown"),
                position=data.get("position", "Unknown"),
                brand=data.get("brand", "Unknown"),
                set_name=data.get("set_name", "Unknown"),
                subset=data.get("subset", ""),
                card_number=data.get("card_number", "Unknown"),
                parallel=data.get("parallel", "Base"),
                is_rookie=data.get("is_rookie", False),
                is_auto=data.get("is_auto", False),
                is_patch=data.get("is_patch", False),
                is_memorabilia=data.get("is_memorabilia", False),
                is_numbered=data.get("is_numbered", False),
                numbering=data.get("numbering", ""),
                is_ssp=data.get("is_ssp", False),
                ssp_type=data.get("ssp_type", ""),
                confidence=float(data.get("confidence", 0.5)),
                identification_notes=data.get("identification_notes", ""),
                raw_response=raw_text
            )
            
        except json.JSONDecodeError as e:
            return CardIdentification(
                confidence=0.0,
                identification_notes=f"Failed to parse response: {str(e)}",
                raw_response=raw_text if 'raw_text' in locals() else ""
            )
        except Exception as e:
            return CardIdentification(
                confidence=0.0,
                identification_notes=f"Error: {str(e)}"
            )
    
    def batch_identify(self, image_paths: List[str], 
                       progress_callback=None) -> List[CardIdentification]:
        """
        Identify multiple cards.
        
        Args:
            image_paths: List of paths to card images
            progress_callback: Optional function(current, total, result) for progress updates
            
        Returns:
            List of CardIdentification objects
        """
        results = []
        total = len(image_paths)
        
        for i, path in enumerate(image_paths):
            result = self.identify_card(path)
            results.append(result)
            
            if progress_callback:
                progress_callback(i + 1, total, result)
        
        return results


# Convenience function for quick identification
def identify_card_quick(image_path: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Quick function to identify a card and return dict.
    
    Args:
        image_path: Path to card image
        api_key: Optional API key
        
    Returns:
        Dictionary with identification results
    """
    identifier = CardIdentifier(api_key)
    result = identifier.identify_card(image_path)
    return result.to_dict()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python card_identifier_v2.py <image_path>")
        print("\nThis will identify the card and print results.")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    print(f"Identifying card: {image_path}")
    print("-" * 50)
    
    identifier = CardIdentifier()
    result = identifier.identify_card(image_path)
    
    print(f"\n📋 CARD IDENTIFICATION RESULTS")
    print("=" * 50)
    print(f"Player: {result.player_name}")
    print(f"Team: {result.team}")
    print(f"Year: {result.year}")
    print(f"Sport: {result.sport}")
    print(f"Position: {result.position}")
    print("-" * 50)
    print(f"Brand: {result.brand}")
    print(f"Set: {result.set_name}")
    if result.subset:
        print(f"Subset: {result.subset}")
    print(f"Parallel: {result.parallel}")
    print(f"Card #: {result.card_number}")
    print("-" * 50)
    
    attrs = result.get_special_attributes()
    if attrs:
        print(f"Special: {' | '.join(attrs)}")
    else:
        print("Special: None")
    
    if result.is_ssp:
        print(f"SSP Type: {result.ssp_type}")
    
    print("-" * 50)
    print(f"Confidence: {result.confidence:.0%}")
    if result.identification_notes:
        print(f"Notes: {result.identification_notes}")
    
    print("\n" + "=" * 50)
    print(f"Summary: {result.summary()}")

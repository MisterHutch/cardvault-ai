"""
Sports Card Binder Page Scanner
Detects and crops individual cards from a 3x3 binder page photo.

Author: HutchGroup LLC
"""

import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional
import uuid
from dataclasses import dataclass
import base64


@dataclass
class DetectedCard:
    """Represents a single detected card from a binder page."""
    image: np.ndarray
    position: Tuple[int, int]  # Row, Column (0-indexed)
    confidence: float
    bounds: Tuple[int, int, int, int]  # x, y, width, height
    
    def to_base64(self) -> str:
        """Convert card image to base64 for API calls."""
        _, buffer = cv2.imencode('.jpg', self.image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        return base64.b64encode(buffer).decode('utf-8')
    
    def save(self, output_dir: Path, prefix: str = "card") -> Path:
        """Save the card image to disk."""
        filename = f"{prefix}_r{self.position[0]}_c{self.position[1]}_{uuid.uuid4().hex[:8]}.jpg"
        output_path = output_dir / filename
        cv2.imwrite(str(output_path), self.image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        return output_path


class CardDetector:
    """
    Detects and extracts individual cards from binder page photos.
    Optimized for standard 3x3 card sleeve pages.
    """
    
    def __init__(self, grid_rows: int = 3, grid_cols: int = 3):
        self.grid_rows = grid_rows
        self.grid_cols = grid_cols
        self.min_card_area_ratio = 0.02  # Minimum card area as ratio of image
        self.max_card_area_ratio = 0.20  # Maximum card area as ratio of image
        
    def detect_cards(self, image_path: str, method: str = "auto") -> List[DetectedCard]:
        """
        Main entry point - detects cards from an image.
        
        Args:
            image_path: Path to the binder page image
            method: Detection method - "auto", "grid", "contour", or "hybrid"
            
        Returns:
            List of DetectedCard objects
        """
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not load image: {image_path}")
        
        # Try different methods based on selection
        if method == "auto":
            # Try grid-based first (most reliable for standard binder pages)
            cards = self._detect_grid_based(image)
            if len(cards) < 4:  # If grid detection fails, try contour
                cards = self._detect_contour_based(image)
        elif method == "grid":
            cards = self._detect_grid_based(image)
        elif method == "contour":
            cards = self._detect_contour_based(image)
        elif method == "hybrid":
            cards = self._detect_hybrid(image)
        else:
            raise ValueError(f"Unknown method: {method}")
            
        return cards
    
    def _detect_grid_based(self, image: np.ndarray) -> List[DetectedCard]:
        """
        Grid-based detection - divides image into equal parts.
        Best for well-aligned binder page photos.
        """
        height, width = image.shape[:2]
        cards = []
        
        # Calculate cell dimensions with some margin
        margin_x = int(width * 0.02)
        margin_y = int(height * 0.02)
        
        cell_width = (width - 2 * margin_x) // self.grid_cols
        cell_height = (height - 2 * margin_y) // self.grid_rows
        
        # Standard trading card aspect ratio is approximately 2.5" x 3.5" = 0.714
        card_aspect_ratio = 2.5 / 3.5
        
        for row in range(self.grid_rows):
            for col in range(self.grid_cols):
                # Calculate cell boundaries
                x1 = margin_x + col * cell_width
                y1 = margin_y + row * cell_height
                x2 = x1 + cell_width
                y2 = y1 + cell_height
                
                # Extract cell
                cell = image[y1:y2, x1:x2]
                
                # Try to find actual card within the cell
                card_img, card_bounds = self._extract_card_from_cell(cell)
                
                if card_img is not None:
                    # Adjust bounds to full image coordinates
                    adj_bounds = (
                        x1 + card_bounds[0],
                        y1 + card_bounds[1],
                        card_bounds[2],
                        card_bounds[3]
                    )
                    
                    cards.append(DetectedCard(
                        image=card_img,
                        position=(row, col),
                        confidence=0.9,
                        bounds=adj_bounds
                    ))
                else:
                    # Use the whole cell if card extraction fails
                    cards.append(DetectedCard(
                        image=cell,
                        position=(row, col),
                        confidence=0.6,
                        bounds=(x1, y1, cell_width, cell_height)
                    ))
        
        return cards
    
    def _extract_card_from_cell(self, cell: np.ndarray) -> Tuple[Optional[np.ndarray], Tuple[int, int, int, int]]:
        """
        Extract the actual card from a grid cell, removing sleeve/pocket edges.
        """
        height, width = cell.shape[:2]
        
        # Convert to grayscale
        gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
        
        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        
        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None, (0, 0, width, height)
        
        # Find the largest rectangular contour
        best_contour = None
        best_area = 0
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > best_area and area > (width * height * 0.3):
                # Approximate the contour
                peri = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
                
                # Check if it's roughly rectangular (4 corners)
                if len(approx) >= 4:
                    best_contour = contour
                    best_area = area
        
        if best_contour is not None:
            x, y, w, h = cv2.boundingRect(best_contour)
            
            # Add small padding
            pad = 5
            x = max(0, x - pad)
            y = max(0, y - pad)
            w = min(width - x, w + 2 * pad)
            h = min(height - y, h + 2 * pad)
            
            card_img = cell[y:y+h, x:x+w]
            return card_img, (x, y, w, h)
        
        # Fallback: crop a standard card shape from center
        card_aspect = 2.5 / 3.5
        if width / height > card_aspect:
            # Cell is wider than card - crop sides
            new_width = int(height * card_aspect)
            x_offset = (width - new_width) // 2
            card_img = cell[:, x_offset:x_offset + new_width]
            return card_img, (x_offset, 0, new_width, height)
        else:
            # Cell is taller than card - crop top/bottom
            new_height = int(width / card_aspect)
            y_offset = (height - new_height) // 2
            card_img = cell[y_offset:y_offset + new_height, :]
            return card_img, (0, y_offset, width, new_height)
    
    def _detect_contour_based(self, image: np.ndarray) -> List[DetectedCard]:
        """
        Contour-based detection - finds card edges directly.
        Better for pages that aren't perfectly aligned.
        """
        height, width = image.shape[:2]
        min_area = width * height * self.min_card_area_ratio
        max_area = width * height * self.max_card_area_ratio
        
        # Preprocess
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Edge detection
        edges = cv2.Canny(blurred, 50, 150)
        
        # Dilate to connect edges
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=2)
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        cards = []
        card_bounds = []
        
        for contour in contours:
            area = cv2.contourArea(contour)
            
            if min_area < area < max_area:
                # Approximate to polygon
                peri = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
                
                # Check if roughly rectangular
                if 4 <= len(approx) <= 8:
                    x, y, w, h = cv2.boundingRect(contour)
                    aspect_ratio = w / h
                    
                    # Trading cards are roughly 2.5x3.5 (aspect ~0.71)
                    if 0.5 < aspect_ratio < 0.9:
                        card_bounds.append((x, y, w, h, area))
        
        # Sort by position (top-left to bottom-right)
        card_bounds.sort(key=lambda b: (b[1] // (height // 3), b[0]))
        
        for idx, (x, y, w, h, _) in enumerate(card_bounds[:9]):  # Max 9 cards
            card_img = image[y:y+h, x:x+w]
            row = idx // 3
            col = idx % 3
            
            cards.append(DetectedCard(
                image=card_img,
                position=(row, col),
                confidence=0.85,
                bounds=(x, y, w, h)
            ))
        
        return cards
    
    def _detect_hybrid(self, image: np.ndarray) -> List[DetectedCard]:
        """
        Hybrid approach - uses grid as guide, contours for refinement.
        """
        # Start with grid detection
        grid_cards = self._detect_grid_based(image)
        
        # For each cell, try to refine with contour detection
        refined_cards = []
        
        for card in grid_cards:
            x, y, w, h = card.bounds
            cell = image[y:y+h, x:x+w]
            
            # Try contour detection on this cell
            cell_cards = self._detect_contour_based(cell)
            
            if cell_cards and cell_cards[0].confidence > card.confidence:
                # Use the contour-detected version
                refined = cell_cards[0]
                refined.position = card.position
                # Adjust bounds to full image
                rx, ry, rw, rh = refined.bounds
                refined.bounds = (x + rx, y + ry, rw, rh)
                refined_cards.append(refined)
            else:
                refined_cards.append(card)
        
        return refined_cards
    
    def visualize_detection(self, image_path: str, cards: List[DetectedCard], output_path: str):
        """
        Create a visualization of detected cards for debugging.
        """
        image = cv2.imread(image_path)
        
        for card in cards:
            x, y, w, h = card.bounds
            color = (0, 255, 0) if card.confidence > 0.8 else (0, 165, 255)
            cv2.rectangle(image, (x, y), (x + w, y + h), color, 3)
            
            label = f"R{card.position[0]}C{card.position[1]} ({card.confidence:.0%})"
            cv2.putText(image, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.6, color, 2)
        
        cv2.imwrite(output_path, image)


def process_binder_page(image_path: str, output_dir: str) -> List[Path]:
    """
    Convenience function to process a binder page and save individual cards.
    
    Args:
        image_path: Path to the binder page image
        output_dir: Directory to save cropped cards
        
    Returns:
        List of paths to saved card images
    """
    detector = CardDetector()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    cards = detector.detect_cards(image_path)
    
    saved_paths = []
    for card in cards:
        path = card.save(output_path)
        saved_paths.append(path)
        print(f"Saved card at position {card.position} -> {path}")
    
    return saved_paths


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python card_detector.py <image_path> [output_dir]")
        sys.exit(1)
    
    image_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "./processed"
    
    paths = process_binder_page(image_path, output_dir)
    print(f"\nProcessed {len(paths)} cards")

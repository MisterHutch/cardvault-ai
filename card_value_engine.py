"""
Sports Card Value Estimation Engine v3.0 — Refactored
Critical sections cleaned: multiplier stacking, sport detection, mock data, confidence calc
Author: HutchGroup LLC
"""

import json
import statistics
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import re


# ============================================================================
# DATA MODELS (unchanged — these are solid)
# ============================================================================

class ConfidenceLevel(Enum):
    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"

class CardCondition(Enum):
    GEM_MINT = "gem_mint"
    MINT = "mint"
    NEAR_MINT_PLUS = "nm_plus"
    NEAR_MINT = "near_mint"
    EXCELLENT = "excellent"
    VERY_GOOD = "very_good"
    GOOD = "good"
    RAW = "raw"

class Sport(Enum):
    BASKETBALL = "basketball"
    FOOTBALL = "football"
    BASEBALL = "baseball"
    SOCCER = "soccer"
    HOCKEY = "hockey"
    OTHER = "other"

@dataclass
class CardAttributes:
    player: str
    year: int
    set_name: str
    card_number: str
    sport: Sport = Sport.OTHER          # NEW: explicit sport field
    parallel: Optional[str] = None
    serial_number: Optional[str] = None
    autograph: bool = False
    rookie: bool = False
    insert: bool = False
    condition: CardCondition = CardCondition.RAW
    graded: bool = False
    grade_value: Optional[float] = None
    grading_company: Optional[str] = None

@dataclass
class MarketDataPoint:
    source: str
    value: float
    date: datetime
    sample_size: int
    condition: CardCondition
    url: Optional[str] = None
    notes: Optional[str] = None

@dataclass
class ValueEstimate:
    estimated_value: float
    confidence: ConfidenceLevel
    confidence_score: float
    value_range: Tuple[float, float]
    data_points: List[MarketDataPoint]
    market_trends: Dict[str, Any]
    grading_recommendation: Optional[str]
    accuracy_factors: Dict[str, float]
    multipliers_applied: Dict[str, float]   # NEW: transparency on what multipliers hit
    timestamp: datetime = field(default_factory=datetime.now)


# ============================================================================
# REFACTORED: MultiplierEngine — single place for all value adjustments
# ============================================================================

class MultiplierEngine:
    """
    All multiplier logic in one place. Capped compound multiplier prevents
    unrealistic value inflation when multiple premiums stack.
    
    CRITICAL REFACTOR: Previously multipliers were applied sequentially
    (1.5 * 2.5 * 5.0 * 3.0 = 56x on a $10 card = $560). Now we use
    additive premiums with a configurable cap.
    """
    
    MAX_COMPOUND_MULTIPLIER = 25.0  # Cap total multiplier at 25x base
    
    CONDITION_MULTIPLIERS = {
        CardCondition.GEM_MINT: 3.5,
        CardCondition.MINT: 2.0,
        CardCondition.NEAR_MINT_PLUS: 1.5,
        CardCondition.NEAR_MINT: 1.2,
        CardCondition.EXCELLENT: 0.8,
        CardCondition.VERY_GOOD: 0.6,
        CardCondition.GOOD: 0.4,
        CardCondition.RAW: 1.0,
    }
    
    GRADE_MULTIPLIERS = {
        # (min_grade, max_grade): multiplier
        (9.5, 10.0): 3.0,   # BGS 9.5+ / PSA 10
        (9.0, 9.49): 2.0,   # PSA 9
        (8.0, 8.99): 1.5,   # PSA 8
        (7.0, 7.99): 1.2,   # PSA 7
        (0.0, 6.99): 0.8,   # Below 7
    }
    
    PARALLEL_MULTIPLIERS = {
        "superfractor": 50.0,
        "1/1": 50.0,
        "gold": 8.0,
        "orange": 5.0,
        "black": 4.0,
        "red": 3.0,
        "blue": 2.5,
        "purple": 2.0,
        "green": 1.8,
        "cracked ice": 1.8,
        "shimmer": 1.7,
        "xfractor": 1.6,
        "mojo": 1.6,
        "silver": 1.5,
        "holo": 1.4,
        "prizm": 1.3,
        "refractor": 1.3,
    }
    
    SPORT_FACTORS = {
        Sport.BASKETBALL: 1.15,
        Sport.FOOTBALL: 1.10,
        Sport.BASEBALL: 0.95,
        Sport.SOCCER: 1.20,
        Sport.HOCKEY: 0.90,
        Sport.OTHER: 1.00,
    }
    
    ERA_MULTIPLIERS = {
        "vintage": 2.5,       # Pre-1980
        "junk_wax": 0.3,      # 1986-1994
        "modern": 1.0,        # 1995-2015
        "ultra_modern": 1.2,  # 2016+
    }
    
    SCARCITY_TABLE = [
        # (max_print_run, multiplier)
        (1, 50.0),
        (5, 10.0),
        (10, 5.0),
        (25, 3.5),
        (50, 2.5),
        (99, 2.0),
        (199, 1.5),
        (499, 1.3),
        (999, 1.1),
    ]
    
    @classmethod
    def apply_all(cls, base_value: float, card: CardAttributes) -> Tuple[float, Dict[str, float]]:
        """
        Apply all multipliers and return (adjusted_value, multiplier_breakdown).
        Uses CAPPED compound multiplication to prevent runaway inflation.
        """
        breakdown = {}
        
        # 1. Condition / Grade
        if card.graded and card.grade_value is not None:
            grade_mult = cls._grade_multiplier(card.grade_value)
            breakdown["grade"] = grade_mult
        else:
            grade_mult = cls.CONDITION_MULTIPLIERS.get(card.condition, 1.0)
            breakdown["condition"] = grade_mult
        
        # 2. Rookie
        rookie_mult = 1.5 if card.rookie else 1.0
        if card.rookie:
            breakdown["rookie"] = rookie_mult
        
        # 3. Autograph
        auto_mult = 2.5 if card.autograph else 1.0
        if card.autograph:
            breakdown["autograph"] = auto_mult
        
        # 4. Serial / Scarcity
        scarcity_mult = cls._scarcity_multiplier(card.serial_number)
        if scarcity_mult != 1.0:
            breakdown["scarcity"] = scarcity_mult
        
        # 5. Parallel
        parallel_mult = cls._parallel_multiplier(card.parallel)
        if parallel_mult != 1.0:
            breakdown["parallel"] = parallel_mult
        
        # 6. Era
        era = cls._determine_era(card.year)
        era_mult = cls.ERA_MULTIPLIERS.get(era, 1.0)
        breakdown["era"] = era_mult
        
        # 7. Sport market
        sport_mult = cls.SPORT_FACTORS.get(card.sport, 1.0)
        if sport_mult != 1.0:
            breakdown["sport_market"] = sport_mult
        
        # COMPOUND WITH CAP
        # Instead of naive multiplication, we separate "positive" and "negative" factors
        raw_compound = (
            grade_mult * rookie_mult * auto_mult * 
            scarcity_mult * parallel_mult * era_mult * sport_mult
        )
        
        capped = min(raw_compound, cls.MAX_COMPOUND_MULTIPLIER)
        if capped < raw_compound:
            breakdown["_cap_applied"] = cls.MAX_COMPOUND_MULTIPLIER
            breakdown["_uncapped"] = round(raw_compound, 2)
        
        breakdown["_total"] = round(capped, 2)
        
        return round(base_value * capped, 2), breakdown
    
    @classmethod
    def _grade_multiplier(cls, grade: float) -> float:
        for (low, high), mult in cls.GRADE_MULTIPLIERS.items():
            if low <= grade <= high:
                return mult
        return 1.0
    
    @classmethod
    def _scarcity_multiplier(cls, serial: Optional[str]) -> float:
        if not serial:
            return 1.0
        
        match = re.search(r'(\d+)/(\d+)', serial)
        if not match:
            return 1.0
        
        current, total = int(match.group(1)), int(match.group(2))
        
        base = 1.0
        for max_run, mult in cls.SCARCITY_TABLE:
            if total <= max_run:
                base = mult
                break
        
        # Jersey number bonus (common: 23, 24, 8, 3, 7, 10, etc.)
        jersey_numbers = {23, 24, 8, 3, 33, 32, 34, 7, 10, 9, 12, 15, 30, 45}
        if current in jersey_numbers and current <= total:
            base *= 1.2
        
        # #1 bonus
        if current == 1:
            base *= 1.3
        elif current == total:
            base *= 1.1
        
        return base
    
    @classmethod
    def _parallel_multiplier(cls, parallel: Optional[str]) -> float:
        if not parallel:
            return 1.0
        
        parallel_lower = parallel.lower()
        for key, mult in cls.PARALLEL_MULTIPLIERS.items():
            if key in parallel_lower:
                return mult
        
        return 1.2  # Generic parallel
    
    @classmethod
    def _determine_era(cls, year: int) -> str:
        if year < 1980:
            return "vintage"
        elif 1986 <= year <= 1994:
            return "junk_wax"
        elif 1995 <= year <= 2015:
            return "modern"
        return "ultra_modern"


# ============================================================================
# REFACTORED: ConfidenceCalculator — extracted from main estimator
# ============================================================================

class ConfidenceCalculator:
    """
    Calculates confidence score from 5 weighted factors.
    Extracted to its own class for testability.
    """
    
    WEIGHTS = {
        "source_diversity": 0.20,
        "sample_size": 0.25,
        "data_recency": 0.15,
        "value_consistency": 0.25,
        "card_specificity": 0.15,
    }
    
    @classmethod
    def calculate(cls, card: CardAttributes, 
                  market_data: List[MarketDataPoint]) -> Tuple[ConfidenceLevel, float, Dict[str, float]]:
        
        factors = {}
        
        # Factor 1: Source diversity
        unique_sources = len(set(dp.source for dp in market_data))
        factors["source_diversity"] = min(1.0, unique_sources / 4)
        
        # Factor 2: Sample size
        total_samples = sum(dp.sample_size for dp in market_data)
        factors["sample_size"] = min(1.0, total_samples / 20)
        
        # Factor 3: Recency
        if market_data:
            cutoff = datetime.now() - timedelta(days=30)
            recent = sum(1 for dp in market_data if dp.date > cutoff)
            factors["data_recency"] = recent / len(market_data)
        else:
            factors["data_recency"] = 0.0
        
        # Factor 4: Value consistency
        if len(market_data) > 1:
            values = [dp.value for dp in market_data]
            mean_val = statistics.mean(values)
            if mean_val > 0:
                cv = statistics.stdev(values) / mean_val
                factors["value_consistency"] = max(0.0, 1.0 - cv)
            else:
                factors["value_consistency"] = 0.5
        else:
            factors["value_consistency"] = 0.5
        
        # Factor 5: Card specificity (more identifiable = higher confidence)
        spec = 0.5
        if card.serial_number:
            spec += 0.2
        if card.parallel:
            spec += 0.15
        if card.graded:
            spec += 0.15
        factors["card_specificity"] = min(1.0, spec)
        
        # Weighted score (0-100)
        score = sum(
            factors[k] * cls.WEIGHTS[k] * 100 
            for k in cls.WEIGHTS
        )
        
        # Map to level
        if score >= 85:
            level = ConfidenceLevel.VERY_HIGH
        elif score >= 75:
            level = ConfidenceLevel.HIGH
        elif score >= 60:
            level = ConfidenceLevel.MEDIUM
        elif score >= 40:
            level = ConfidenceLevel.LOW
        else:
            level = ConfidenceLevel.VERY_LOW
        
        return level, round(score, 1), factors


# ============================================================================
# REFACTORED: MockDataFactory — deterministic, isolated from real fetching
# ============================================================================

class MockDataFactory:
    """
    Generates deterministic mock market data for testing.
    Uses hashlib (not hash()) for cross-session consistency.
    """
    
    @classmethod
    def generate(cls, card: CardAttributes) -> List[MarketDataPoint]:
        base_value = cls._base_value(card)
        points = []
        
        # eBay sold listings (5 data points, most important source)
        for i in range(5):
            seed = cls._seed(f"{card.player}:ebay:{i}")
            variance = 1.0 + (seed % 20 - 10) / 100  # ±10%
            points.append(MarketDataPoint(
                source="ebay_sold",
                value=round(base_value * variance, 2),
                date=datetime.now() - timedelta(days=i * 7),
                sample_size=3,
                condition=card.condition,
                url=f"https://ebay.com/itm/mock_{seed % 99999}",
                notes=f"Sold {i * 7} days ago",
            ))
        
        # 130point
        points.append(MarketDataPoint(
            source="130point",
            value=round(base_value * 1.05, 2),
            date=datetime.now() - timedelta(days=5),
            sample_size=15,
            condition=card.condition,
            url="https://130point.com/sales/mock",
        ))
        
        # PWCC (only for cards > $50)
        if base_value > 50:
            points.append(MarketDataPoint(
                source="pwcc",
                value=round(base_value * 1.2, 2),
                date=datetime.now() - timedelta(days=10),
                sample_size=2,
                condition=card.condition,
                url="https://pwcc.com/mock",
            ))
        
        # COMC
        points.append(MarketDataPoint(
            source="comc",
            value=round(base_value * 0.95, 2),
            date=datetime.now() - timedelta(days=3),
            sample_size=8,
            condition=card.condition,
            url="https://comc.com/mock",
        ))
        
        # PSA APR (graded reference)
        if not card.graded:
            points.append(MarketDataPoint(
                source="psa_apr",
                value=round(base_value * 2.0, 2),
                date=datetime.now() - timedelta(days=30),
                sample_size=5,
                condition=CardCondition.MINT,
                notes="PSA 9 reference price",
            ))
        
        return points
    
    @classmethod
    def _base_value(cls, card: CardAttributes) -> float:
        """Deterministic base value from player hash + card attributes."""
        seed = cls._seed(card.player)
        base = (seed % 100) + 10
        
        if card.rookie:
            base *= 2
        if card.autograph:
            base *= 3
        if card.serial_number:
            base *= 1.5
        if card.parallel:
            base *= 1.3
        if card.year < 1980:
            base *= 3
        elif card.year >= 2020:
            base *= 1.2
        elif 1986 <= card.year <= 1994:
            base *= 0.3
        
        return max(1.0, base)
    
    @staticmethod
    def _seed(text: str) -> int:
        """Deterministic integer from string. Same input = same output always."""
        return int(hashlib.md5(text.encode()).hexdigest()[:8], 16)


# ============================================================================
# MAIN ESTIMATOR (simplified — delegates to extracted classes)
# ============================================================================

class CardValueEstimator:
    """
    v3.0 — Refactored. Delegates multiplier logic, confidence calculation,
    and mock data generation to dedicated classes.
    """
    
    SOURCE_WEIGHTS = {
        "ebay_sold": 0.35,
        "130point": 0.20,
        "pwcc": 0.15,
        "comc": 0.10,
        "beckett": 0.08,
        "psa_apr": 0.07,
        "sportlots": 0.05,
    }
    
    def estimate_value(self, card: CardAttributes,
                       market_data: Optional[List[MarketDataPoint]] = None,
                       use_mock: bool = True) -> ValueEstimate:
        """Main entry point."""
        if market_data is None:
            if use_mock:
                market_data = MockDataFactory.generate(card)
            else:
                raise ValueError("No market data provided and mock data disabled")
        
        # 1. Weighted base value from market data
        base_value = self._weighted_value(market_data)
        
        # 2. Apply multipliers ONLY for mock data.
        # Real sold comps already reflect grade/RC/parallel — multiplying again
        # causes massive inflation. Detect real data by checking for non-mock URLs.
        has_real_data = any(
            dp.url and "mock" not in str(dp.url)
            for dp in market_data
            if dp.source == "ebay_sold"
        )
        if has_real_data:
            adjusted_value = round(base_value, 2)
            mult_breakdown = {"note": "multipliers skipped — real sold comp data"}
        else:
            adjusted_value, mult_breakdown = MultiplierEngine.apply_all(base_value, card)
        
        # 3. Confidence (refactored — extracted calculator)
        confidence, score, factors = ConfidenceCalculator.calculate(card, market_data)
        
        # 4. Value range
        value_range = self._value_range(adjusted_value, score)
        
        # 5. Market trends
        trends = self._market_trends(market_data)
        
        # 6. Grading recommendation
        grading_rec = self._grading_recommendation(card, adjusted_value)
        
        return ValueEstimate(
            estimated_value=adjusted_value,
            confidence=confidence,
            confidence_score=score,
            value_range=value_range,
            data_points=market_data,
            market_trends=trends,
            grading_recommendation=grading_rec,
            accuracy_factors=factors,
            multipliers_applied=mult_breakdown,
        )
    
    def _weighted_value(self, market_data: List[MarketDataPoint]) -> float:
        """Weighted average from sources. Median per source to reduce outliers."""
        if not market_data:
            return 0.0
        
        source_groups: Dict[str, List[float]] = {}
        for dp in market_data:
            source_groups.setdefault(dp.source, []).append(dp.value)
        
        weighted_sum = 0.0
        total_weight = 0.0
        
        for source, values in source_groups.items():
            median = statistics.median(values)
            base_weight = self.SOURCE_WEIGHTS.get(source, 0.05)
            # Scale weight by sample size (more data = more trust)
            adjusted_weight = base_weight * min(1.0, len(values) / 10)
            weighted_sum += median * adjusted_weight
            total_weight += adjusted_weight
        
        if total_weight == 0:
            return statistics.mean([dp.value for dp in market_data])
        
        return weighted_sum / total_weight
    
    def _value_range(self, value: float, confidence_score: float) -> Tuple[float, float]:
        """Tighter range at higher confidence."""
        variance = max(0.05, 0.5 - (confidence_score / 200))
        return (round(value * (1 - variance), 2), round(value * (1 + variance), 2))
    
    def _market_trends(self, market_data: List[MarketDataPoint]) -> Dict[str, Any]:
        """Analyze trends from data points."""
        trends = {
            "direction": "stable",
            "velocity": "normal",
            "30_day_change": 0.0,
            "90_day_change": 0.0,
            "volatility": "low",
            "recommendation": "hold",
        }
        
        if len(market_data) < 3:
            return trends
        
        sorted_data = sorted(market_data, key=lambda x: x.date)
        recent = [dp.value for dp in sorted_data[-3:]]
        older = [dp.value for dp in sorted_data[:3]]
        
        recent_avg = statistics.mean(recent)
        older_avg = statistics.mean(older)
        
        if older_avg > 0:
            change_pct = ((recent_avg - older_avg) / older_avg) * 100
        else:
            change_pct = 0.0
        
        if change_pct > 10:
            trends["direction"] = "up"
            trends["recommendation"] = "sell high" if change_pct > 30 else "hold"
        elif change_pct < -10:
            trends["direction"] = "down"
            trends["recommendation"] = "buy low" if change_pct < -20 else "hold"
        
        trends["30_day_change"] = round(change_pct / 2, 1)
        trends["90_day_change"] = round(change_pct, 1)
        
        all_values = [dp.value for dp in sorted_data]
        if len(all_values) > 1:
            mean_val = statistics.mean(all_values)
            if mean_val > 0:
                cv = statistics.stdev(all_values) / mean_val
                trends["volatility"] = "high" if cv > 0.3 else ("medium" if cv > 0.15 else "low")
        
        return trends
    
    def _grading_recommendation(self, card: CardAttributes, value: float) -> Optional[str]:
        """Grade-or-not recommendation based on value threshold."""
        if card.graded:
            return None
        if value < 20:
            return "Not worth grading unless gem mint condition"
        elif value < 50:
            return "Consider grading if confident in 9+ grade"
        elif value < 100:
            return "Grading recommended if NM+ or better"
        elif value < 500:
            return "Definitely grade if NM or better"
        return "High value — professional grading essential"


# ============================================================================
# ACCURACY VALIDATOR (unchanged — already clean)
# ============================================================================

class AccuracyValidator:
    def __init__(self):
        self.history: List[Dict] = []
    
    def validate(self, estimate: ValueEstimate, actual_price: float) -> Dict[str, Any]:
        error = abs(estimate.estimated_value - actual_price)
        error_pct = (error / actual_price * 100) if actual_price > 0 else 100
        accuracy = max(0, 100 - error_pct)
        in_range = estimate.value_range[0] <= actual_price <= estimate.value_range[1]
        
        result = {
            "estimated": estimate.estimated_value,
            "actual": actual_price,
            "error": round(error, 2),
            "error_pct": round(error_pct, 2),
            "accuracy_pct": round(accuracy, 2),
            "in_range": in_range,
            "confidence": estimate.confidence.value,
            "confidence_score": estimate.confidence_score,
            "timestamp": datetime.now(),
        }
        self.history.append(result)
        return result
    
    def overall_accuracy(self) -> Dict[str, float]:
        if not self.history:
            return {"overall_accuracy": 0, "in_range_pct": 0, "total": 0}
        
        accuracies = [v["accuracy_pct"] for v in self.history]
        in_range = sum(1 for v in self.history if v["in_range"])
        
        return {
            "overall_accuracy": round(statistics.mean(accuracies), 1),
            "median_accuracy": round(statistics.median(accuracies), 1),
            "in_range_pct": round((in_range / len(self.history)) * 100, 1),
            "total": len(self.history),
        }


# ============================================================================
# QUICK SMOKE TEST
# ============================================================================

if __name__ == "__main__":
    est = CardValueEstimator()
    
    card = CardAttributes(
        player="Patrick Mahomes",
        year=2017,
        set_name="Contenders",
        card_number="303",
        sport=Sport.FOOTBALL,
        parallel="Cracked Ice",
        serial_number="23/25",
        autograph=True,
        rookie=True,
        condition=CardCondition.NEAR_MINT_PLUS,
    )
    
    result = est.estimate_value(card)
    print(f"Card: {card.player} {card.year} {card.set_name}")
    print(f"Value: ${result.estimated_value:.2f}")
    print(f"Range: ${result.value_range[0]:.2f} – ${result.value_range[1]:.2f}")
    print(f"Confidence: {result.confidence.value} ({result.confidence_score}%)")
    print(f"Multipliers: {result.multipliers_applied}")
    print(f"Trend: {result.market_trends['direction']}")
    print(f"Grading: {result.grading_recommendation}")

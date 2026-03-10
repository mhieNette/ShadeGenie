# sample_colors.py
# Foundation shade sample colors for Shade Genie
# Robust mapping: case/spacing insensitive

RAW_SAMPLE_COLORS = {
    ("Maybelline Fit Me", "Natural Beige (220)"): "#e3bca2",
    ("L'Oreal Paris Infallible 24H Tinted Serum Foundation", "3-4 Light-Medium"): "#e6c3a8",
    ("MAC Studio Fix", "NC42"): "#c49a6c",
    ("Fenty Beauty Pro Filt'r", "310"): "#d1a074",
    ("Estée Lauder Double Wear", "3W1 Tawny"): "#d9ab7d",
    ("NARS Sheer Glow", "Punjab (Medium 1)"): "#e8be8f",
    ("Revlon ColorStay", "Buff (150)"): "#f0cfb5",
    ("Clinique Even Better", "Cream Chamois (VF-N)"): "#e6c6a3",
    ("Bobbi Brown Skin Long-Wear", "Warm Beige"): "#d9b08b",
    ("Dior Forever", "2N Neutral"): "#e7c7a6",
    ("Lancôme Teint Idole Ultra Wear", "320 Bisque W"): "#ddb48f",
    ("Giorgio Armani Luminous Silk", "5.5"): "#d6ad87",
    ("Too Faced Born This Way", "Warm Beige"): "#dcb48e",
    ("Urban Decay Stay Naked", "40NN"): "#e0bea0",
    ("Charlotte Tilbury Airbrush Flawless", "6 Neutral"): "#dfbfa3",
    ("Huda Beauty #FauxFilter", "Toasted Coconut 240N"): "#d9b496",
    ("Pat McGrath Labs Skin Fetish", "Medium 15"): "#d6b094",
    ("bareMinerals Original", "Medium Beige 12"): "#d8b08a",
    ("IT Cosmetics CC+ Cream", "Medium"): "#d9b18c",
    ("Shiseido Synchro Skin", "Neutral 3"): "#e0bfa1",
    ("L'Oreal True Match", "1N Ivory"): "#f1d6c1",
    ("Maybelline Fit Me Matte + Poreless", "115 Ivory"): "#f3d8cc",
    ("Revlon ColorStay", "110 Ivory"): "#efd2bb",
    ("L'Oreal Infallible Pro-Matte", "101 Classic Ivory"): "#f2d3b0",
    ("Maybelline SuperStay Skin Tint", "102"): "#e8c8a8",
}

def _norm(s: str) -> str:
    # normalize case + trim + collapse inner spaces
    s = (s or "").strip().lower()
    s = " ".join(s.split())
    return s

# This is the dict you will use everywhere
sample_colors = {(_norm(b), _norm(sh)): hexv for (b, sh), hexv in RAW_SAMPLE_COLORS.items()}

def get_sample_color(brand: str, shade: str):
    """Return hex color for (brand, shade) using normalization, or None."""
    return sample_colors.get((_norm(brand), _norm(shade)))

"""Generate high-quality summary visuals matching the PPTX color scheme."""
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parent
FIG_DIR = ROOT / "reports" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# PPTX Color Palette
BG_NAVY = "#0A1628"      # Matches the slide background perfectly
BOX_NAVY = "#162A50"     # Slightly lighter navy for dimension tables
TEAL = "#00D4AA"         # Medical Teal for borders/accents
ORANGE = "#FF6B35"       # Safety Orange for the Fact table
WHITE = "#FFFFFF"
MUTED = "#8BAFC8"

def build_star_schema(path: Path) -> None:
    # Set the background color to match the PPTX slide
    fig, ax = plt.subplots(figsize=(12, 7), facecolor=BG_NAVY)
    ax.set_facecolor(BG_NAVY)
    ax.axis("off")

    def box(x, y, w, h, title, subtitle, bg_color, border_color):
        p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.05", 
                           fc=bg_color, ec=border_color, lw=2.5, zorder=2)
        ax.add_patch(p)
        ax.text(x + w / 2, y + h * 0.65, title, color=WHITE, 
                ha="center", va="center", fontsize=15, fontweight="bold", family="sans-serif", zorder=3)
        ax.text(x + w / 2, y + h * 0.35, subtitle, color=MUTED, 
                ha="center", va="center", fontsize=12, family="sans-serif", zorder=3)

    # Draw connection lines (zorder=1)
    ax.plot([0.5, 0.25], [0.5, 0.75], color=TEAL, lw=2, zorder=1, alpha=0.8)
    ax.plot([0.5, 0.75], [0.5, 0.75], color=TEAL, lw=2, zorder=1, alpha=0.8)
    ax.plot([0.5, 0.25], [0.5, 0.25], color=TEAL, lw=2, zorder=1, alpha=0.8)
    ax.plot([0.5, 0.75], [0.5, 0.25], color=TEAL, lw=2, zorder=1, alpha=0.8)
    
    # Central Fact Table (Orange)
    box(0.35, 0.4, 0.3, 0.2, "FACT_ADVERSE_EVENT", "Severity, Polypharmacy, TTO", ORANGE, WHITE)
    
    # Dimension Tables (Navy with Teal borders)
    box(0.05, 0.7, 0.3, 0.15, "DIM_PATIENT", "Age, Weight, Sex, Country", BOX_NAVY, TEAL)
    box(0.65, 0.7, 0.3, 0.15, "DIM_TIME", "Event Date, Drug Start Date", BOX_NAVY, TEAL)
    box(0.05, 0.15, 0.3, 0.15, "DIM_OUTCOME", "Severity Label, Reaction Term", BOX_NAVY, TEAL)
    box(0.65, 0.15, 0.3, 0.15, "DIM_DRUG", "Active Ingredient, Role", BOX_NAVY, TEAL)

    plt.title("Relational Data Warehouse: Star Schema Architecture", 
              fontsize=22, fontweight="bold", color=WHITE, pad=20)
    plt.tight_layout()
    # Save with the navy background
    plt.savefig(path, dpi=300, bbox_inches="tight", facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print("✅ High-fidelity slide-matching Star Schema generated.")

def build_summary(path: Path, star_path: Path) -> None:
    images = [
        ("PRR Forest Plot (Signal Detection)", FIG_DIR / "prr_forest_plot.png"),
        ("Model Showdown: Recall vs Precision", FIG_DIR / "classification_results.png"),
        ("Top Predictors of Severity (is_us Bias)", FIG_DIR / "extended_rf_feature_importances.png"),
        ("Predictive Model Metrics", FIG_DIR / "extended_model_comparison_table.png"),
        ("PCA Explained Variance", FIG_DIR / "extended_pca_scree.png"),
        ("Star Schema Architecture", star_path),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(20, 12), facecolor=WHITE)
    fig.suptitle("Key Analytics & Visual Deliverables", fontsize=24, fontweight='bold', color=BG_NAVY, y=0.98)
    
    for ax, (title, img_path) in zip(axes.ravel(), images):
        ax.axis("off")
        if img_path.exists():
            img = mpimg.imread(img_path)
            ax.imshow(img)
            ax.set_title(title, fontsize=14, fontweight='bold', color=BG_NAVY, pad=15)
        else:
            ax.text(0.5, 0.5, f"Missing: {img_path.name}", ha="center", va="center", color=ORANGE)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print("✅ High-fidelity Visual Summary generated.")

if __name__ == "__main__":
    schema_path = FIG_DIR / "star_schema.png"
    build_star_schema(schema_path)
    build_summary(FIG_DIR / "summary_visuals.png", schema_path)
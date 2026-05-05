"""Generate high-quality summary visuals and a modern star schema diagram."""
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parent
FIG_DIR = ROOT / "reports" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# Project Color Palette
NAVY = "#0A1628"
TEAL = "#00D4AA"
ORANGE = "#FF6B35"
MUTED = "#8BAFC8"

def build_star_schema(path: Path) -> None:
    plt.figure(figsize=(10, 6), facecolor='white')
    ax = plt.gca()
    ax.axis("off")

    def box(x, y, w, h, title, subtitle, color):
        # Create a modern rounded rectangle
        p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05", 
                           fc=color, ec="white", lw=2)
        ax.add_patch(p)
        ax.text(x + w / 2, y + h / 2 + 0.05, title, color="white", 
                ha="center", va="center", fontsize=12, fontweight="bold", family="sans-serif")
        ax.text(x + w / 2, y + h / 2 - 0.05, subtitle, color="white", 
                ha="center", va="center", fontsize=9, family="sans-serif", alpha=0.9)

    # Draw connection lines (behind boxes)
    ax.plot([0.5, 0.2], [0.5, 0.75], color=MUTED, lw=2, zorder=0)
    ax.plot([0.5, 0.8], [0.5, 0.75], color=MUTED, lw=2, zorder=0)
    ax.plot([0.5, 0.2], [0.5, 0.25], color=MUTED, lw=2, zorder=0)
    ax.plot([0.5, 0.8], [0.5, 0.25], color=MUTED, lw=2, zorder=0)
    
    # Draw boxes (zorder=1 to sit on top of lines)
    box(0.35, 0.4, 0.3, 0.2, "FACT_ADVERSE_EVENT", "Severity, Polypharmacy, TTO", ORANGE)
    box(0.05, 0.7, 0.25, 0.15, "DIM_PATIENT", "Age, Weight, Sex, Country", NAVY)
    box(0.7, 0.7, 0.25, 0.15, "DIM_TIME", "Event Date, Drug Start Date", NAVY)
    box(0.05, 0.15, 0.25, 0.15, "DIM_OUTCOME", "Severity Label, Reaction Term", NAVY)
    box(0.7, 0.15, 0.25, 0.15, "DIM_DRUG", "Active Ingredient, Role", NAVY)

    plt.title("Relational Data Warehouse: Star Schema Architecture", 
              fontsize=16, fontweight="bold", color=NAVY, pad=20)
    plt.tight_layout()
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()

def build_summary(path: Path, star_path: Path) -> None:
    images = [
        ("PRR Forest Plot (Signal Detection)", FIG_DIR / "prr_forest_plot.png"),
        ("Model Showdown: Recall vs Precision", FIG_DIR / "classification_results.png"),
        ("Top Predictors of Severity (is_us Bias)", FIG_DIR / "extended_rf_feature_importances.png"),
        ("Predictive Model Metrics", FIG_DIR / "extended_model_comparison_table.png"),
        ("PCA Explained Variance", FIG_DIR / "extended_pca_scree.png"),
        ("Star Schema Architecture", star_path),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(20, 12), facecolor='white')
    fig.suptitle("Key Analytics & Visual Deliverables", fontsize=24, fontweight='bold', color=NAVY, y=0.98)
    
    for ax, (title, img_path) in zip(axes.ravel(), images):
        ax.axis("off")
        if img_path.exists():
            img = mpimg.imread(img_path)
            ax.imshow(img)
            ax.set_title(title, fontsize=14, fontweight='bold', color=NAVY, pad=15)
        else:
            ax.text(0.5, 0.5, f"Missing: {img_path.name}", ha="center", va="center", color=ORANGE)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print("✅ High-fidelity Teal & Orange visuals generated successfully.")

if __name__ == "__main__":
    schema_path = FIG_DIR / "star_schema.png"
    build_star_schema(schema_path)
    build_summary(FIG_DIR / "summary_visuals.png", schema_path)
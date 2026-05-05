"""Generate high-quality summary visuals collage and star schema diagram.

Outputs:
- reports/figures/star_schema.png
- reports/figures/summary_visuals.png
"""
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parent
FIG_DIR = ROOT / "reports" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)


def build_star_schema(path: Path) -> None:
    plt.figure(figsize=(8, 5))
    ax = plt.gca()
    ax.axis("off")

    def box(x, y, w, h, text, color="#1B6CA8"):
        ax.add_patch(Rectangle((x, y), w, h, facecolor=color, edgecolor="white", lw=1))
        ax.text(
            x + w / 2,
            y + h / 2,
            text,
            color="white",
            ha="center",
            va="center",
            fontsize=10,
            fontweight="bold",
        )

    box(0.4, 0.42, 0.2, 0.16, "Fact\nAdverse Event", "#2E7D32")
    box(0.1, 0.7, 0.25, 0.15, "Dim Patient", "#1B6CA8")
    box(0.65, 0.7, 0.25, 0.15, "Dim Time", "#1B6CA8")
    box(0.1, 0.15, 0.25, 0.15, "Dim Outcome", "#1B6CA8")
    box(0.65, 0.15, 0.25, 0.15, "Dim Drug", "#1B6CA8")
    box(0.65, 0.42, 0.25, 0.15, "Dim Reaction", "#1B6CA8")

    ax.plot([0.4, 0.35], [0.5, 0.77], color="gray")
    ax.plot([0.6, 0.65], [0.5, 0.77], color="gray")
    ax.plot([0.4, 0.35], [0.5, 0.22], color="gray")
    ax.plot([0.6, 0.65], [0.5, 0.22], color="gray")
    ax.plot([0.6, 0.65], [0.5, 0.5], color="gray")

    plt.title("Star Schema (GLP-1 FAERS)", fontsize=12, fontweight="bold")
    plt.tight_layout()
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close()


def build_summary(path: Path, star_path: Path) -> None:
    images = [
        ("PRR Forest Plot", FIG_DIR / "prr_forest_plot.png"),
        ("Confusion Matrix & ROC", FIG_DIR / "classification_results.png"),
        ("RF Feature Importance", FIG_DIR / "extended_rf_feature_importances.png"),
        ("Model Comparison", FIG_DIR / "extended_model_comparison_table.png"),
        ("PCA Scree", FIG_DIR / "extended_pca_scree.png"),
        ("Star Schema", star_path),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    for ax, (title, img_path) in zip(axes.ravel(), images):
        ax.axis("off")
        if img_path.exists():
            img = mpimg.imread(img_path)
            ax.imshow(img)
            ax.set_title(title, fontsize=10)
        else:
            ax.text(0.5, 0.5, f"Missing:\n{img_path.name}", ha="center", va="center")

    plt.tight_layout()
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close()


def main() -> None:
    star_path = FIG_DIR / "star_schema.png"
    build_star_schema(star_path)
    build_summary(FIG_DIR / "summary_visuals.png", star_path)
    print("Created", star_path)
    print("Created", FIG_DIR / "summary_visuals.png")


if __name__ == "__main__":
    main()
